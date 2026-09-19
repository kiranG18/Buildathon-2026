"""Unauthenticated summary for the sign-in screen, plus the golden-set and coach endpoints for the Prompts screen."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.analytics.rollups import stats
from backend.core.db import Db
from backend.core.security import User, db_dep, require
from evals import coach, runner

router = APIRouter()
mgr = require("Admin", "Manager")


class VersionBody(BaseModel):
    version: int | None = None


@router.get("/public/campaigns")
def public_campaigns(db: Db = Depends(db_dep)) -> list[dict]:
    out = []
    for c in db.q("select id, name, status, objective from campaigns where status in ('live', 'paused') order by id"):
        s = stats(db, c["id"])
        out.append({"id": c["id"], "name": c["name"], "status": c["status"], "objective": c["objective"], "prospects": s["prospects"], "replies": s["replies"], "meetings": s["meetings"]})
    return out


@router.post("/campaigns/{cid}/prompts/{role}/golden")
def golden(cid: str, role: str, body: VersionBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    r = runner.run(db, cid, role, body.version)
    return {k: r[k] for k in ("score", "passed", "total", "method", "version")} | {"failing": [x for x in r["results"] if not x["ok"]]}


@router.post("/campaigns/{cid}/prompts/{role}/coach")
def coach_prompt(cid: str, role: str, body: VersionBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    version = body.version or db.q1("select version from prompt_versions where campaign_id = %s and agent_key = %s and status = 'active'", (cid, role))["version"]
    return coach.suggest(db, cid, role, version, user)
