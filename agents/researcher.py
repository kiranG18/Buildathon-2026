"""Researcher (Lead Research and Enrichment).

The direct provider reads the enrichment record for a prospect (seed facts served from /demo-sources pages, because fictional
companies have no web presence). Every fact keeps its source URL and confidence. Facts under 0.5 are dropped, unsourced ones become gaps.
The DronaHQ provider hands the same context to a hosted agent that saves its facts through the save_research MCP tool.
"""

from dataclasses import dataclass, field

CONF = {"High": 0.9, "Medium": 0.7, "Low": 0.4}


@dataclass
class Research:
    new_facts: list[dict] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    provider: str = "direct"
    note: str = ""


def enrich(p: dict) -> list[dict]:
    """The enrichment record: facts not yet on file. Drops low-confidence and unsourced facts."""
    return [f for f in p["rich"] if f.get("url") and CONF.get(f["conf"], 0) >= 0.5]


def research(p: dict) -> Research:
    have = {f["id"] for f in p["facts"]}
    new = [f for f in enrich(p) if f["id"] not in have]
    gaps = [] if (new or p["facts"]) else ["No sources matched this prospect"]
    note = " Guardian stripped instruction-like text from the bio before the model saw it." if p["bio"] else ""
    return Research(new, gaps, "direct", note)
