"""Chunk rules from the plan: by heading, 250 to 350 tokens with a 40-token overlap.
Pair-style docs (objections, examples, voice scripts) split per paragraph and never mid-message.
A file may pin chunk ids with <!-- K-207 --> markers, which keeps citations stable across reingest.
"""

import re

import yaml

MARK = re.compile(r"^<!--\s*(K-[A-Za-z0-9]+)\s*-->\s*$", re.M)
PARAGRAPH_TYPES = {"objections", "examples", "voice script", "icp", "case study"}


def parse_frontmatter(raw: str) -> tuple[dict, str]:
    if raw.startswith("---"):
        _, fm, body = raw.split("---", 2)
        return yaml.safe_load(fm) or {}, body.strip()
    return {}, raw.strip()


def tokens(text: str) -> int:
    return max(1, len(text.split()))


def _window(text: str, size: int = 300, overlap: int = 40) -> list[str]:
    words = text.split()
    if len(words) <= size:
        return [text.strip()]
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i : i + size]))
        if i + size >= len(words):
            break
        i += size - overlap
    return out


def chunk_text(doc_type: str, body: str) -> list[tuple[str | None, str]]:
    """Return (pinned_id or None, text) pairs."""
    if MARK.search(body):
        parts = MARK.split(body)
        return [(parts[i], parts[i + 1].strip()) for i in range(1, len(parts) - 1, 2) if parts[i + 1].strip()]
    if doc_type in PARAGRAPH_TYPES:
        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        return [(None, p) for p in paras]
    sections = re.split(r"(?m)^#{1,3}\s+", body)
    out: list[tuple[str | None, str]] = []
    for sec in sections:
        sec = sec.strip()
        if sec:
            out.extend((None, w) for w in _window(sec))
    return out
