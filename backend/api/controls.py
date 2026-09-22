import secrets
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.core import clock
from backend.core.db import Db
from backend.core.errors import CadenceError, Forbidden, NotFound, StateConflict
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
    email: str | None = None
    rep_limit: int = 30


class RepPatch(BaseModel):
    rep_limit: int = Field(ge=0, le=500)


class ProfilePatch(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    title: str = Field(default="", max_length=80)


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
def add_user(body: UserBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    """An admin or manager adds a rep, manager or admin. The generated password is returned once and only its hash is stored."""
    if body.role == "Admin" and user["role"] != "Admin":
        raise Forbidden("Only an Admin can create an Admin account")
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


@router.patch("/users/{uid}")
def patch_profile(uid: str, body: ProfilePatch, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    """Edit a rep's, manager's or admin's name and title. Email, role and password have their own flows."""
    u = get_user(db, uid)
    if not u:
        raise NotFound("User not found")
    name, title = body.name.strip(), body.title.strip()
    db.x("update users set name = %s, title = %s where id = %s", (name, title, uid))
    act(db, None, "agent", f"{user['name']} edited {u['name']}'s profile", agent="Manager")
    return {"name": name, "title": title}


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
def offboard(rid: str, body: ReassignBody | None = None, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
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


@router.delete("/reps/{rid}")
def delete_rep(rid: str, replacement_rep_id: str | None = None, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    """Remove a rep. A rep who still holds campaigns, open prospects or open escalations needs a replacement first.
    A rep that past records point to is kept as an offboarded user so the history still shows who handled it."""
    u = get_user(db, rid)
    if not u or u["role"] != "Rep":
        raise NotFound("Rep not found")
    aff = _affected(db, rid)
    if (aff["campaigns"] or aff["open_escalations"] or aff["enrollments"]) and not replacement_rep_id:
        raise StateConflict("This rep still holds work. Pick a replacement rep to take it over.", code="rep_has_work", extra={"affected": aff})
    if replacement_rep_id:
        if replacement_rep_id == rid:
            raise CadenceError("Pick a different rep as the replacement", code="validation_error")
        _move(db, rid, replacement_rep_id)
    db.x("delete from rep_assignments where rep_id = %s", (rid,))
    try:
        with db.conn.transaction():
            db.x("delete from users where id = %s", (rid,))
        removed = True
    except psycopg.errors.ForeignKeyViolation:
        db.x("update users set active = false where id = %s", (rid,))
        removed = False
    act(db, None, "agent", f"{user['name']} deleted rep {u['name']}" + ("" if removed else ", kept as offboarded because past records refer to them"), agent="Manager")
    return {"deleted": removed, "kept_as_offboarded": not removed, "reassigned_to": replacement_rep_id}


@router.post("/reps/{rid}/reassign")
def reassign(rid: str, body: ReassignBody, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
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

@router.get("/suppression")
def list_suppression(user: User = Depends(current_user), db: Db = Depends(db_dep)) -> list[dict]:
    rows = db.q("select * from suppression_list order by created_at desc")
    return [
        {"id": s["id"], "kind": s["kind"], "value": s["value"], "reason": s["reason"], "added_by": s.get("added_by") or "System", "by": s.get("added_by") or "System", "at": clock.ms(s["created_at"]) if s.get("created_at") else None}
        for s in rows
    ]


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
    canonical_key = {"email": "gmail", "sms": "twilio"}.get(key, key)
    return {"replanned": controls.set_integration_paused(db, canonical_key, body.paused, user)}


@router.post("/integrations/{key}/mode")
def integ_mode(key: str, body: IntegMode, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    canonical_key = {"email": "gmail", "sms": "twilio"}.get(key, key)
    if body.mode not in ("live", "sandbox"):
        raise CadenceError("mode must be live or sandbox", code="validation_error")
    row = db.q1("select * from integrations where key = %s", (canonical_key,))
    if not row:
        raise NotFound("Unknown integration")
    if body.mode == "live" and not row["can_live"]:
        raise StateConflict(f"{row['name']} cannot run live")
    db.x("update integrations set mode = %s where key = %s", (body.mode, canonical_key))
    return {"mode": body.mode}


@router.post("/integrations/{key}/test")
def integ_test(key: str, user: User = Depends(mgr), db: Db = Depends(db_dep)) -> dict:
    canonical_key = {"email": "gmail", "sms": "twilio"}.get(key, key)
    row = db.q1("select * from integrations where key = %s", (canonical_key,))
    if not row:
        raise NotFound("Unknown integration")
    from backend.channels.base import REGISTRY

    adapter = REGISTRY.get({"gmail": "email", "twilio": "sms", "linkedin": "linkedin"}.get(canonical_key, ""))
    ok, err = row["status"] == "ok", row["err"]
    if adapter is not None:
        try:
            adapter.test()
            ok, err = True, None
        except Exception as exc:
            ok, err = False, str(getattr(exc, "message", exc))
    elif canonical_key in ("gmail", "twilio") and row["mode"] == "live":
        ok, err = False, "No credentials are configured, so this channel cannot go live."
    db.x("update integrations set last_check = %s, status = %s, err = %s where key = %s", (clock.now(), "ok" if ok else "error", err, canonical_key))
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
