from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.core import clock
from backend.core.db import Db
from backend.core.errors import NotFound
from backend.core.security import User, current_user, db_dep, require
from backend.orchestrator import prompts_svc

router = APIRouter()
mgr = require("Admin", "Manager")


class SaveBody(BaseModel):
    agent_key: str
    body: str
    note: str | None = None
    parent_version: int | None = None


class ActivateBody(BaseModel):
    rollback: bool = False


@router.get("/campaigns/{cid}/prompts")
def list_prompts(cid: str, agent: str | None = None, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> list[dict]:
    out: dict[str, list] = {}
    for v in prompts_svc.list_versions(db, cid, agent):
        author = db.q1("select name from users where id = %s", (v["author_id"],))
        out.setdefault(v["agent_key"], []).append(
            {"id": v["id"], "version": v["version"], "status": v["status"], "author": author["name"] if author else None, "created_at": clock.ms(v["created_at"]),
             "note": v["change_note"], "runs": v["runs"], "golden_score": (v["gold"] or [None, None])[1], "lines": v["lines"]}
        )
    return [{"agent_key": k, "versions": vs} for k, vs in out.items()]


@router.post("/campaigns/{cid}/prompts", status_code=201)
def save_prompt(cid: str, body: SaveBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return prompts_svc.save_version(db, cid, body.agent_key, body.body, user, body.note, body.parent_version)


@router.get("/campaigns/{cid}/prompts/diff")
def diff_prompts(cid: str, agent: str, from_version: int, to_version: int, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    return {"hunks": prompts_svc.diff(db, cid, agent, from_version, to_version)}


@router.post("/prompts/{version_id}/activate")
def activate_prompt(version_id: str, body: ActivateBody | None = None, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    row = db.q1("select campaign_id, agent_key, version from prompt_versions where id = %s", (version_id,))
    if not row:
        raise NotFound("Prompt version not found")
    return prompts_svc.activate(db, row["campaign_id"], row["agent_key"], row["version"], user, rollback=bool(body and body.rollback))
