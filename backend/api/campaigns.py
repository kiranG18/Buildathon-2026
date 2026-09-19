from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.analytics.rollups import stats
from backend.core import clock
from backend.core.db import Db
from backend.core.errors import Forbidden
from backend.core.security import User, current_user, db_dep, require
from backend.orchestrator import campaigns_svc, controls, discovery
from backend.orchestrator.repo import campaign

router = APIRouter()
mgr = require("Admin", "Manager")


class CampaignBody(BaseModel):
    name: str
    objective: str = ""
    icp: str | None = None
    roles: list[str] = []
    geo_list: list[str] = []
    exclusions: list[str] = []
    refs: str = ""
    tone: str = ""
    thr: int = 70
    daily_send_cap: int = 30
    first: bool = False
    voice: bool = True
    reply: bool = True
    channels: dict[str, bool] = {}
    agents: dict[str, bool] = {}
    rep_ids: list[str] = []
    doc_ids: list[str] = []
    tpl: str | None = None


class CampaignPatch(BaseModel):
    name: str | None = None
    objective: str | None = None
    icp: str | None = None
    tone: str | None = None
    refs: str | None = None
    thr: int | None = None
    daily_send_cap: int | None = None
    priority: int | None = None
    appr: dict[str, bool] | None = None
    ch_limit: dict[str, int] | None = None
    roles: list[str] | None = None
    geo_list: list[str] | None = None
    exclusions: list[str] | None = None
    rep_ids: list[str] | None = None
    doc_ids: list[str] | None = None


class ReasonBody(BaseModel):
    reason: str | None = None


class AgentBody(BaseModel):
    enabled: bool | None = None
    provider: str | None = None


class ChannelBody(BaseModel):
    enabled: bool | None = None
    daily_limit: int | None = None


class DiscoverBody(BaseModel):
    count: int = 5


class ImportBody(BaseModel):
    text: str


class DuplicateBody(BaseModel):
    name: str | None = None


def _can_see(db: Db, user: User, campaign_id: str) -> None:
    if user.is_rep and not db.q1("select 1 as x from rep_assignments where rep_id = %s and campaign_id = %s and active", (user["id"], campaign_id)):
        raise Forbidden("This campaign belongs to other reps")


@router.get("/campaigns")
def list_campaigns(status: str | None = None, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> list[dict]:
    rows = db.q("select id, name, status, icp, owner_id, last_activity from campaigns" + (" where status = %s" if status else " where status <> 'archived'") + " order by id", (status,) if status else ())
    out = []
    for r in rows:
        if user.is_rep and not db.q1("select 1 as x from rep_assignments where rep_id = %s and campaign_id = %s and active", (user["id"], r["id"])):
            continue
        s = stats(db, r["id"])
        out.append({"id": r["id"], "name": r["name"], "status": r["status"], "icp_summary": r["icp"], "owner": r["owner_id"], "last_activity": clock.ms(r["last_activity"]),
                    "counts": {"prospects": s["prospects"], "outreach": s["touches"], "replies": s["replies"], "meetings": s["meetings"]}})
    return out


@router.post("/campaigns", status_code=201)
def create_campaign(body: CampaignBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return campaigns_svc.create(db, body.model_dump(), user)


@router.get("/campaigns/{cid}")
def get_campaign(cid: str, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    _can_see(db, user, cid)
    c = campaign(db, cid)
    return {**{k: v for k, v in c.items() if k not in ("paused_at", "created_at", "last_activity")}, "checklist": campaigns_svc.checklist(db, cid), "volume": campaigns_svc.volume_estimate(c)}


@router.patch("/campaigns/{cid}")
def patch_campaign(cid: str, body: CampaignPatch, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return campaigns_svc.update(db, cid, body.model_dump(exclude_unset=True), user)


@router.get("/campaigns/{cid}/dashboard")
def dashboard(cid: str, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    _can_see(db, user, cid)
    return campaigns_svc.dashboard(db, cid)


@router.post("/campaigns/{cid}/dry-run")
def dry_run(cid: str, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return campaigns_svc.dry_run(db, cid)


@router.post("/campaigns/{cid}/activate")
def activate(cid: str, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return campaigns_svc.activate(db, cid, user)


@router.post("/campaigns/{cid}/pause")
def pause(cid: str, body: ReasonBody | None = None, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return controls.pause_campaign(db, cid, user, body.reason if body else None)


@router.post("/campaigns/{cid}/resume")
def resume(cid: str, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return controls.resume_campaign(db, cid, user)


@router.post("/campaigns/{cid}/complete")
def complete(cid: str, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return campaigns_svc.close(db, cid, user, "completed")


@router.post("/campaigns/{cid}/archive")
def archive(cid: str, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return campaigns_svc.close(db, cid, user, "archived")


@router.post("/campaigns/{cid}/duplicate", status_code=201)
def duplicate(cid: str, body: DuplicateBody | None = None, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return campaigns_svc.duplicate(db, cid, user, body.name if body else None)


@router.put("/campaigns/{cid}/agents/{agent}")
def set_agent(cid: str, agent: str, body: AgentBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return controls.toggle_agent(db, cid, agent, user, body.enabled, body.provider)


@router.put("/campaigns/{cid}/channels/{channel}")
def set_channel(cid: str, channel: str, body: ChannelBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return controls.toggle_channel(db, cid, channel, user, body.enabled, body.daily_limit)


@router.post("/campaigns/{cid}/discover")
def discover(cid: str, body: DiscoverBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    made = discovery.discover(db, cid, min(max(body.count, 1), 10), user)
    return {"enrolled_ids": [e["id"] for e in made]}


@router.post("/campaigns/{cid}/prospects/import")
def import_prospects(cid: str, body: ImportBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    rows = [[x.strip() for x in line.split(",")] for line in body.text.splitlines() if line.strip()]
    return discovery.import_rows(db, cid, rows, user)
