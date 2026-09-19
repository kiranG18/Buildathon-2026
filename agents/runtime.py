"""Shared plumbing for the agent modules: the active prompt bundle and code-chosen retrieval plans."""

from dataclasses import dataclass

from backend.core.config import get_settings
from backend.core.db import Db
from rag import retrieve

SYSTEM_ROLE = "System"


def live() -> bool:
    return get_settings().llm_mode in ("live", "record", "replay")


@dataclass
class Bundle:
    system: list[str]
    agent: list[str]
    system_version: int
    agent_version: int


def bundle(db: Db, campaign_id: str, role: str, agent_version: int | None = None) -> Bundle:
    """The active System prompt plus the agent prompt (a specific version when replaying)."""

    def lines(r: str, v: int | None = None) -> tuple[list[str], int]:
        sql = "select lines, version from prompt_versions where campaign_id = %s and agent_key = %s and " + ("version = %s" if v else "status = 'active'")
        row = db.q1(sql, (campaign_id, r, v) if v else (campaign_id, r))
        return (row["lines"], row["version"]) if row else ([], 1)

    s, sv = lines(SYSTEM_ROLE)
    a, av = lines(role, agent_version)
    return Bundle(s, a, sv, av)


def plan_query(p: dict, task: str) -> str:
    """Retrieval queries come from structured facts and the task, never from scraped page text."""
    return f"{p['title']} {p['ind']} {task}"


def gather(db: Db, campaign_id: str, query: str, specs: list[tuple[list[str], int]]) -> list[dict]:
    """specs: (doc types, k) pairs. Returns unique chunks in plan order."""
    out, seen = [], set()
    for types, k in specs:
        for hit in retrieve.search(db, campaign_id, query, types, k):
            if hit["id"] not in seen:
                seen.add(hit["id"])
                out.append(hit)
    return out


def template_version(db: Db, campaign_id: str, prompt_version: int) -> int:
    """Fake mode renders grounded templates only when the Writer prompt tells the agent to open with a sourced fact.
    Judging the prompt text, not its number, keeps new campaigns (whose version 1 is the grounded harness) correct."""
    row = db.q1("select lines from prompt_versions where campaign_id = %s and agent_key = 'Writer' and version = %s", (campaign_id, prompt_version))
    return 2 if row and any("sourced fact" in line.lower() for line in row["lines"]) else 1
