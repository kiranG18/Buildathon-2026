from datetime import datetime

from fastapi import APIRouter, Depends

from backend.analytics import rollups
from backend.core.db import Db
from backend.core.security import User, db_dep, require

router = APIRouter()
mgr = require("Admin", "Manager")


@router.get("/analytics/campaigns")
def campaigns(from_: datetime | None = None, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> list[dict]:
    out = []
    for c in db.q("select id, name from campaigns where status <> 'archived' order by id"):
        s = rollups.stats(db, c["id"], from_)
        out.append({"campaign_id": c["id"], "name": c["name"], **s, "avg_latency_ms": _latency(db, c["id"])})
    return out


def _latency(db: Db, cid: str) -> int:
    r = db.q1("select coalesce(avg(latency_s), 0) as l from agent_runs where campaign_id = %s and not is_replay", (cid,))
    return round(r["l"] * 1000)


@router.get("/analytics/agents")
def agents(campaign_id: str | None = None, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> list[dict]:
    return rollups.by_agent(db, campaign_id)


@router.get("/analytics/prompt-versions")
def prompt_versions(campaign_id: str | None = None, agent: str | None = None, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> list[dict]:
    return rollups.prompt_versions(db, campaign_id, agent)
