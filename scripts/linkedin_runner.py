"""Send approved-by-you LinkedIn notes from this machine.

LinkedIn has no messaging API and its terms forbid automation, so the deployed site never sends a LinkedIn note. This script is the local hand-off:
it reads the open LinkedIn approvals from a Cadence site, shows each note, and only after you type `y` runs the browser bot in your own signed-in Chrome
(`scripts/linkedin_bot.js`). When the bot succeeds it records the approval on the site, so the touch is stored as LIVE. A failed send leaves the approval open.
Each run is capped and paced. Use a test account and expect LinkedIn's own limits.

Set the LinkedIn integration to Live in Settings first, sign in once with `node scripts/linkedin_login.js`, then run:
    CADENCE_EMAIL=you@example.com python scripts/linkedin_runner.py            (asks for the password)
Options: --limit 5 (notes per run, at most 10), --pause 45 (minimum seconds between sends), --headed (watch the browser), --dry-run (list only),
--yes (send without asking for each note; the cap and the pauses still apply)."""

import argparse
import getpass
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "https://buildathon-2026-production.up.railway.app"
NOTE_LIMIT = 200
MAX_PER_RUN = 10


def pending_notes(state: dict) -> list[dict]:
    """The open approvals whose message is a LinkedIn note, oldest first, each with the profile to open."""
    msgs = {m["id"]: m for m in state["msgs"]}
    enr = {e["id"]: e for e in state["enr"]}
    people = state["people"]
    out = []
    for a in sorted(state["approvals"], key=lambda x: x["t"]):
        m = msgs.get(a["msgId"]) if a["status"] == "open" and a.get("msgId") else None
        if not m or m["ch"] != "linkedin":
            continue
        p = people[enr[a["eid"]]["pid"]]
        out.append({"approval": a["id"], "name": p["name"], "url": p["linkedin"], "note": m["body"]})
    return out


def as_sent(note: str) -> str:
    """The text the bot really sends: it cuts a note to LinkedIn's 200-character limit the same way."""
    return note if len(note) <= NOTE_LIMIT else note[: NOTE_LIMIT - 3] + "..."


def send(url: str, note: str, headed: bool) -> tuple[bool, str]:
    cmd = ["node", "scripts/linkedin_bot.js", "--url", url, "--note", note] + (["--headed"] if headed else [])
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(ROOT))
    return res.returncode == 0, (res.stderr or res.stdout or "").strip()[-400:]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default=os.getenv("CADENCE_URL", DEFAULT_URL))
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--pause", type=int, default=45)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true", help="send without asking for each note")
    args = ap.parse_args()
    if not 1 <= args.limit <= MAX_PER_RUN:
        sys.exit(f"--limit must be between 1 and {MAX_PER_RUN}.")

    email = os.getenv("CADENCE_EMAIL") or input("Cadence email (a manager or admin): ").strip()
    password = os.getenv("CADENCE_PASSWORD") or getpass.getpass("Password: ")
    with httpx.Client(base_url=args.url, timeout=60) as api:
        login = api.post("/auth/login", json={"email": email, "password": password})
        if login.status_code != 200:
            sys.exit("Sign-in failed. Check the email and password.")
        api.headers["Authorization"] = "Bearer " + login.json()["token"]
        state = api.get("/state").json()
        if state["integ"]["linkedin"]["mode"] != "live":
            sys.exit("LinkedIn is in Sandbox. Set it to Live in Settings, Integrations, so the sends are recorded as LIVE.")
        todo = pending_notes(state)[: args.limit]
        if not todo:
            sys.exit("No LinkedIn notes are waiting for approval.")
        sent = 0
        for i, n in enumerate(todo):
            print(f"\n[{i + 1}/{len(todo)}] {n['name']}  {n['url']}\n{as_sent(n['note'])}")
            if args.dry_run:
                continue
            answer = "y" if args.yes else input("Send this note from your LinkedIn account? [y/N/q] ").strip().lower()
            if answer == "q":
                break
            if answer != "y":
                continue
            ok, detail = send(n["url"], n["note"], args.headed)
            if not ok:
                print("Not sent. The approval stays open.\n" + detail)
                continue
            body = {"decision": "approve", "edited_body": as_sent(n["note"]) if as_sent(n["note"]) != n["note"] else None}
            res = api.post(f"/approvals/{n['approval']}/decide", json=body).json()
            print(res.get("msg", "Recorded."))
            sent += 1
            if sent < len(todo) and i < len(todo) - 1:
                wait = args.pause + random.randint(0, 45)
                print(f"Waiting {wait} seconds before the next one.")
                time.sleep(wait)
        print(f"\nDone. {sent} note(s) sent.")


if __name__ == "__main__":
    main()
