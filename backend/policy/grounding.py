"""Grounding check: every claim must trace to a real source, numbers must appear in that source, banned phrases never pass.

Runs in code after the Writer or Responder returns. No model can override it.
"""

import re

from backend.core.db import Db

BANNED = ("guaranteed", "100%", "revolutionary", "best-in-class")
_NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


WORD_NUMS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14", "fifteen": "15",
    "sixteen": "16", "seventeen": "17", "eighteen": "18", "nineteen": "19", "twenty": "20"
}


def _numbers(text: str) -> set[str]:
    nums = {n.strip(",") for n in _NUM.findall(text)}
    low = text.lower()
    for word, digit in WORD_NUMS.items():
        if re.search(r"\b" + word + r"\b", low):
            nums.add(digit)
            nums.add(word)
    return nums


def source_text(db: Db, src: str, p: dict, campaign_id: str) -> str | None:
    """Return the text of the cited source, or None when the id is unknown or invisible to this campaign."""
    if not src or src == "?":
        return None
    src = src.strip("[](){}<>.,;: ")
    candidates = [src]
    if src.isdigit():
        candidates.extend([f"F{src}", f"K-{src}", f"K{src}"])
    elif not src.startswith(("F", "K")):
        candidates.extend([f"F{src}", f"K-{src}"])
    elif src.startswith("K") and not src.startswith("K-"):
        candidates.append(f"K-{src[1:]}")
    for s in candidates:
        if s.startswith("F"):
            for f in [*p.get("facts", []), *p.get("rich", [])]:
                if f.get("id") == s or str(f.get("id")).lstrip("F") == src:
                    return f["text"]
        if s.startswith("K"):
            row = db.q1(
                "select content from knowledge_chunks where (id = %s or origin_id = %s) and (scope = 'global' or campaign_id = %s) limit 1",
                (s, s, campaign_id),
            )
            if row:
                return row["content"]
    for s in candidates:
        row = db.q1(
            "select content from knowledge_chunks where (id = %s or origin_id = %s) and (scope = 'global' or campaign_id = %s) limit 1",
            (s, s, campaign_id),
        )
        if row:
            return row["content"]
    return None


CALL_DURATIONS = {"10", "15", "20", "25", "30", "45", "60", "90"}


def _known_ids_numbers(db: Db, p: dict, campaign_id: str) -> set[str]:
    nums = set()
    for f in [*p.get("facts", []), *p.get("rich", [])]:
        nums |= _numbers(str(f.get("id", "")))
        nums |= _numbers(str(f.get("text", "")))
    for ch in db.q("select id, origin_id, content from knowledge_chunks where scope = 'global' or campaign_id = %s", (campaign_id,)):
        nums |= _numbers(str(ch.get("id", "")))
        nums |= _numbers(str(ch.get("origin_id", "")))
        nums |= _numbers(str(ch.get("content", "")))
    return nums


def check(db: Db, comp: dict, p: dict, campaign_id: str) -> dict:
    """comp holds segs, claims and body. Returns {total, bad: [{t, src, reason}], problems: []}."""
    bad: list[dict] = []
    known_ids = _known_ids_numbers(db, p, campaign_id)
    for cl in comp["claims"]:
        src = cl["src"]
        if src == "?":
            bad.append({**cl, "reason": "no_source"})
            continue
        text = source_text(db, src, p, campaign_id)
        if text is None:
            bad.append({**cl, "reason": "unknown_source"})
            continue
        missing = _numbers(cl["t"]) - _numbers(text) - CALL_DURATIONS - known_ids - _numbers(src)
        if missing:
            bad.append({**cl, "reason": f"number_not_in_source: {sorted(missing)[0]}"})
    low = comp["body"].lower()
    for phrase in BANNED:
        if phrase in low:
            bad.append({"t": phrase, "src": "?", "reason": "banned_phrase"})
    uncited = _numbers(" ".join(s["t"] for s in comp["segs"] if not s.get("src")))
    stray = {n for n in uncited if len(n.strip("$%,")) >= 2 and not re.fullmatch(r"\d{1,2}(:\d\d)?", n)}
    allowed_context = _numbers(comp["body"]) & ({"20", "15", "30", "90", "60", "two-page"} | CALL_DURATIONS | known_ids)
    stray -= allowed_context
    if stray and not comp.get("allow_uncited_numbers"):
        bad.append({"t": sorted(stray)[0], "src": "?", "reason": "unsourced_number"})
    return {"total": len(comp["claims"]), "bad": bad}


def length_problem(comp: dict, channel: str, max_words: int) -> str | None:
    body = comp["body"]
    if channel == "email" and len(body.split()) > max_words:
        return f"email is {len(body.split())} words, limit {max_words}"
    if channel == "linkedin" and len(body) > 300:
        return f"linkedin note is {len(body)} characters, limit 300"
    if channel == "sms" and len(body) > 160:
        return f"sms is {len(body)} characters, limit 160"
    return None
