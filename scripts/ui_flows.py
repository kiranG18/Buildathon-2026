"""Drives the main manager flows in a real browser against a running server and fails on any console error.

python scripts/ui_flows.py [base_url]   (needs the API and a worker, and a freshly reset database)
"""

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"


def step(name: str) -> None:
    print("-", name, flush=True)


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        page = b.new_page(viewport={"width": 1366, "height": 768})
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.goto(BASE)
        page.wait_for_selector(".login")
        page.fill("#lem", "ava@helix.demo")
        page.fill("#lpw", "helix-demo")
        page.click("#lgo")
        page.wait_for_selector(".app")

        step("pause C2 leaves the others running")
        page.evaluate("go('/campaigns/C2/overview')")
        page.click("[data-a=pause][data-id=C2]")
        page.wait_for_selector(".pill.paused")
        page.wait_for_selector(".toast")
        page.screenshot(path=str(OUT / "flow_paused.png"))
        page.evaluate("go('/overview')")
        page.wait_for_selector(".kcard.paused")
        assert page.locator(".kcard .pill.live").count() == 2, "C1 and C3 must still read Live"
        page.evaluate("go('/campaigns/C2/overview')")
        page.click("[data-a=resume][data-id=C2]")
        page.wait_for_selector("[data-a=pause][data-id=C2]")

        step("run Dana end to end")
        page.evaluate("go('/prospects/dana-whitfield')")
        page.click("[data-a=runNow]")
        page.wait_for_selector(".toast")
        deadline = time.time() + 40
        while time.time() < deadline and "Qualified" not in page.inner_text("#view"):
            page.wait_for_timeout(1500)
            page.evaluate("repaint()")
        assert "Qualified" in page.inner_text("#view"), "Dana never reached Qualified"
        page.screenshot(path=str(OUT / "flow_dana_qualified.png"))
        assert "Day 0" in page.inner_text("#view"), "the plan must show its touches"

        step("open the decision trace")
        page.click("#view button.why[data-a=trace] >> nth=0")
        page.wait_for_selector(".drawer")
        assert "Prompt version" in page.inner_text(".drawer") or "This job has not run" in page.inner_text(".drawer")
        page.screenshot(path=str(OUT / "flow_trace.png"))
        page.keyboard.press("Escape")

        step("approve a draft from the inbox")
        page.evaluate("go('/approvals')")
        page.wait_for_selector("[data-a=selAppr]")
        first_kinds = page.inner_text("#apprdetail")
        approve = page.locator("[data-a=approve]").first
        if approve.count():
            approve.click()
            page.wait_for_selector(".toast")
        page.screenshot(path=str(OUT / "flow_approvals.png"))
        _ = first_kinds

        step("simulate a reply and read the classification")
        page.evaluate("go('/prospects/tomas-reyes')")
        page.click("[data-a=simReply]")
        page.click("#srgo")
        page.wait_for_selector(".toast")

        step("kill switch and resume")
        page.click("[data-a=killAsk]")
        page.click("#cfm")
        page.wait_for_selector(".killbar")
        page.screenshot(path=str(OUT / "flow_kill.png"))
        page.click(".killbar [data-a=killOff]")
        page.wait_for_selector(".killbar", state="detached")

        step("save and activate a prompt version, then roll back")
        page.evaluate("go('/campaigns/C1/prompts')")
        page.click("[data-a=prRole][data-k=Writer]")
        page.fill("#prText", "Write the message for the given channel. Tone: concise.\nOpen with one sourced fact about the prospect.\nAdd one customer result from RETRIEVED KNOWLEDGE.\nEnd with one question.\nReturn message and claims[] with a source id for each claim.")
        page.click("[data-a=prSave]")
        page.wait_for_selector(".toast")
        page.click("[data-a=prActivate]")
        page.click("#cfm")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "flow_prompts.png"))
        page.click("[data-a=prRoll]")
        page.click("#cfm")
        page.wait_for_timeout(600)

        step("golden set run and analytics")
        page.click("[data-a=prGold]")
        page.wait_for_selector(".toast")
        page.evaluate("go('/analytics')")
        page.wait_for_selector(".tbl")
        page.screenshot(path=str(OUT / "flow_analytics.png"))

        step("create a campaign from a template and see the checklist")
        page.evaluate("go('/campaigns/new')")
        page.select_option("[data-i=cfTpl]", "C1")
        page.fill("[data-f=name]", "UK Fintech CTOs")
        page.screenshot(path=str(OUT / "flow_create.png"))
        b.close()
    for e in errors:
        print(e)
    print("errors:", len(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
