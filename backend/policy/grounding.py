"""Grounding check: every claim must trace to a real source, numbers must appear in that source, banned phrases never pass.

Runs in code after the Writer or Responder returns. No model can override it.
"""

import re

from backend.core.db import Db

BANNED = ("guaranteed", "100%", "revolutionary", "best-in-class")
_NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


def _numbers(text: str) -> set[str]:
    return {n.strip(",") for n in _NUM.findall(text)}


def source_text(db: Db, src: str, p: dict, campaign_id: str) -> str | None:
    """Return the text of the cited source, or None when the id is unknown or invisible to this campaign."""
    if src.startswith("F"):
        for f in [*p["facts"], *p["rich"]]:
            if f["id"] == src:
                return f["text"]
        return None
    if src.startswith("K"):
        row = db.q1(
            "select content from knowledge_chunks where (id = %s or origin_id = %s) and (scope = 'global' or campaign_id = %s) limit 1",
            (src, src, campaign_id),
        )
        if row:
            return row["content"]
    return None


def check(db: Db, comp: dict, p: dict, campaign_id: str) -> dict:
    """comp holds segs, claims and body. Returns {total, bad: [{t, src, reason}], problems: []}."""
    bad: list[dict] = []
    for cl in comp["claims"]:
        src = cl["src"]
        if src == "?":
            bad.append({**cl, "reason": "no_source"})
            continue
        text = source_text(db, src, p, campaign_id)
        if text is None:
            bad.append({**cl, "reason": "unknown_source"})
            continue
        missing = _numbers(cl["t"]) - _numbers(text)
        if missing:
            bad.append({**cl, "reason": f"number_not_in_source: {sorted(missing)[0]}"})
    low = comp["body"].lower()
    for phrase in BANNED:
        if phrase in low:
            bad.append({"t": phrase, "src": "?", "reason": "banned_phrase"})
    uncited = _numbers(" ".join(s["t"] for s in comp["segs"] if not s.get("src")))
    stray = {n for n in uncited if len(n.strip("$%,")) >= 2 and not re.fullmatch(r"\d{1,2}(:\d\d)?", n)}
    allowed_context = _numbers(comp["body"]) & {"20", "15", "30", "90", "60", "two-page"}
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
