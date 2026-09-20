import secrets
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.core import clock
from backend.core.db import Db
from backend.core.errors import CadenceError, NotFound, StateConflict
from backend.core.security import User, current_user, db_dep, hash_password, require
from backend.orchestrator import controls, replies
from backend.orchestrator.repo import act
from backend.orchestrator.repo import user as get_user

router = APIRouter()
mgr = require("Admin", "Manager")
adm = require("Admin")


class KillBody(BaseModel):
    active: bool
    reason: str | None = None


class ReassignBody(BaseModel):
    replacement_rep_id: str | None = None


class UserBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    role: Literal["Admin", "Manager", "Rep"] = "Rep"
    email: str | None = Field(default=None, max_length=120)
    rep_limit: int = Field(default=30, ge=0, le=500)


class RepPatch(BaseModel):
    rep_limit: int


class SuppressBody(BaseModel):
    kind: str
    value: str
    reason: str = "Added by hand"


class IntegPause(BaseModel):
    paused: bool


class IntegMode(BaseModel):
    mode: str


class ClockBody(BaseModel):
    hours: float = 24


@router.get("/kill-switch")
def kill_state(user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    r = db.q1("select kill_switch, kill_at, kill_by from global_settings where id = 1")
    return {"active": r["kill_switch"], "set_by": r["kill_by"], "set_at": clock.ms(r["kill_at"])}


@router.post("/kill-switch")
def kill_set(body: KillBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return controls.set_kill(db, body.active, user, body.reason)


# --- reps -----------------------------------------------------------------------------------------------------------------

@router.get("/reps")
def reps(user: User = Depends(current_user), db: Db = Depends(db_dep)) -> list[dict]:
    out = []
    for u in db.q("select * from users where role = 'Rep' order by id"):
        out.append({"id": u["id"], "name": u["name"], "status": "active" if u["active"] else "offboarded", "limits": u["rep_limit"], "hours": u["hours"], "channels": u["channels"],
                    "assignments": [r["campaign_id"] for r in db.q("select campaign_id from rep_assignments where rep_id = %s and active", (u["id"],))]})
    return out


@router.post("/users", status_code=201)
def add_user(body: UserBody, user: User = Depends(adm), db: Db = Depends(db_dep)) -> dict:
    """An admin adds a rep, manager or admin. The generated password is returned once and only its hash is stored."""
    slug_ = ".".join(part for part in "".join(ch if ch.isalnum() else " " for ch in body.name.lower()).split())
    email = (body.email or f"{slug_}@helix.demo").strip().lower()
    if "@" not in email or db.q1("select 1 as x from users where lower(email) = %s", (email,)):
        raise StateConflict("That email is missing or already has an account", code="email_taken")
    is_rep = body.role == "Rep"
    n = db.q1("select count(*) as n from users where role = 'Rep'")["n"]
    password = secrets.token_urlsafe(9)
    uid = db.nid("U")
    db.x("insert into users (id, name, role, email, password_hash, title, rep_limit, channels, label) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
         (uid, body.name.strip(), body.role, email, hash_password(password), "Account executive" if is_rep else body.role, body.rep_limit if is_rep else 0,
          ["email", "linkedin"] if is_rep else [], f"Rep {chr(65 + n)}" if is_rep else ""))
    act(db, None, "agent", f"{user['name']} added {body.role.lower()} {body.name.strip()}", agent="Manager")
    return {"id": uid, "email": email, "role": body.role, "password": password}


@router.patch("/reps/{rid}")
def patch_rep(rid: str, body: RepPatch, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    if not db.x("update users set rep_limit = %s where id = %s and role = 'Rep'", (body.rep_limit, rid)):
        raise NotFound("Rep not found")
    return {"limits": body.rep_limit}


def _affected(db: Db, rid: str) -> dict:
    return {
        "campaigns": [r["campaign_id"] for r in db.q("select campaign_id from rep_assignments where rep_id = %s and active", (rid,))],
        "open_escalations": db.q1("select count(*) as n from escalations where rep_id = %s and status = 'open'", (rid,))["n"],
        "enrollments": db.q1("select count(*) as n from enrollments where rep_id = %s and state in ('qualified','contacted','awaiting_approval','replied_pos','replied_obj','escalated')", (rid,))["n"],
    }


@router.get("/reps/{rid}/affected")
def affected(rid: str, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    if not get_user(db, rid):
        raise NotFound("Rep not found")
    return {"affected": _affected(db, rid)}


@router.post("/reps/{rid}/offboard")
def offboard(rid: str, body: ReassignBody | None = None, user: User = Depends(adm), db: Db = Depends(db_dep)) -> dict:
    """Offboarding lists every affected campaign. With a replacement rep it also reassigns; without one, sends defer with no_rep_available."""
    u = get_user(db, rid)
    if not u or u["role"] != "Rep":
        raise NotFound("Rep not found")
    if not u["active"]:
        raise StateConflict("This rep is already offboarded")
    aff = _affected(db, rid)
    db.x("update users set active = false where id = %s", (rid,))
    to = body.replacement_rep_id if body else None
    if to:
        _move(db, rid, to)
    act(db, None, "agent", f"{user['name']} offboarded {u['name']}" + (f", items moved to {get_user(db, to)['name']}" if to else ", items left unassigned"), agent="Manager")
    return {"affected": aff, "reassigned_to": to}


@router.post("/reps/{rid}/reassign")
def reassign(rid: str, body: ReassignBody, user: User = Depends(adm), db: Db = Depends(db_dep)) -> dict:
    if not body.replacement_rep_id:
        raise CadenceError("Pick a replacement rep", code="validation_error")
    return {"moved": _move(db, rid, body.replacement_rep_id)}


def _move(db: Db, frm: str, to: str) -> dict:
    target = get_user(db, to)
    if not target or target["role"] != "Rep" or not target["active"]:
        raise NotFound("Replacement rep not found or offboarded")
    camps = [r["campaign_id"] for r in db.q("select campaign_id from rep_assignments where rep_id = %s and active", (frm,))]
    db.x("update rep_assignments set active = false where rep_id = %s", (frm,))
    for c in camps:
        db.x("insert into rep_assignments (rep_id, campaign_id, active) values (%s,%s,true) on conflict (rep_id, campaign_id) do update set active = true", (to, c))
    n_e = db.x("update enrollments set rep_id = %s where rep_id = %s", (to, frm))
    n_x = db.x("update escalations set rep_id = %s where rep_id = %s and status = 'open'", (to, frm))
    return {"campaigns": camps, "enrollments": n_e, "escalations": n_x}


# --- suppression ----------------------------------------------------------------------------------------------------------

@router.post("/suppression", status_code=201)
def add_suppression(body: SuppressBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    if body.kind not in ("email", "domain", "phone"):
        raise CadenceError("kind must be email, domain or phone", code="validation_error")
    replies.add_suppression(db, body.kind, body.value.strip(), body.reason, user["name"])
    return {"ok": True}


@router.delete("/suppression/{sid}")
def remove_suppression(sid: str, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    if not db.x("delete from suppression_list where id = %s", (sid,)):
        raise NotFound("Suppression entry not found")
    return {"ok": True}


# --- integrations ---------------------------------------------------------------------------------------------------------

@router.post("/integrations/{key}/pause")
def integ_pause(key: str, body: IntegPause, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    return {"replanned": controls.set_integration_paused(db, key, body.paused, user)}


@router.post("/integrations/{key}/mode")
def integ_mode(key: str, body: IntegMode, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    if body.mode not in ("live", "sandbox"):
        raise CadenceError("mode must be live or sandbox", code="validation_error")
    row = db.q1("select * from integrations where key = %s", (key,))
    if not row:
        raise NotFound("Unknown integration")
    if body.mode == "live" and not row["can_live"]:
        raise StateConflict(f"{row['name']} cannot run live")
    db.x("update integrations set mode = %s where key = %s", (body.mode, key))
    return {"mode": body.mode}


@router.post("/integrations/{key}/test")
def integ_test(key: str, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    row = db.q1("select * from integrations where key = %s", (key,))
    if not row:
        raise NotFound("Unknown integration")
    from backend.channels.base import REGISTRY

    adapter = REGISTRY.get({"gmail": "email", "twilio": "sms", "linkedin": "linkedin"}.get(key, ""))
    ok, err = row["status"] == "ok", row["err"]
    if adapter is not None:
        try:
            adapter.test()
            ok, err = True, None
        except CadenceError as exc:
            ok, err = False, exc.message
    elif key in ("gmail", "twilio") and row["mode"] == "live":
        ok, err = False, "No credentials are configured, so this channel cannot go live."
    db.x("update integrations set last_check = %s, status = %s, err = %s where key = %s", (clock.now(), "ok" if ok else "error", err, key))
    return {"ok": ok, "error": err}


# --- demo tools -----------------------------------------------------------------------------------------------------------

@router.post("/demo/advance-clock")
def advance(body: ClockBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    _demo_only()
    return controls.advance_clock(db, body.hours)


class PlayCallBody(BaseModel):
    enrollment_id: str


@router.post("/demo/play-call")
def play_call(body: PlayCallBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    """Replay the DronaHQ Voice post-call path with a scripted transcript, labelled SANDBOX."""
    _demo_only()
    from backend.orchestrator.repo import enrollment as get_enrollment

    e = get_enrollment(db, body.enrollment_id)
    cid = replies.record_call(db, e, sandbox=True)
    e = get_enrollment(db, body.enrollment_id)
    if e["state"] not in ("meeting", "opted_out", "stopped"):
        from agents.util import slots_for

        replies.book_meeting(db, e, slots_for(clock.ms(clock.now()))[0], "Caller")
    return {"call_id": cid}


@router.post("/demo/reset")
def reset(user: User = Depends(adm)) -> dict:
    _demo_only()
    from scripts.load_seed import load

    load()
    return {"ok": True}


def _demo_only() -> None:
    from backend.core.config import get_settings

    if not get_settings().demo_mode:
        raise CadenceError("Demo tools are off", code="demo_disabled", status=403)
