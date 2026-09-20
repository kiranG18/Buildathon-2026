"""The policy gate: ten ordered checks that stand between every agent and every send.

evaluate() answers allow, defer, hold, replan, block or needs_approval and lists every check with a note.
No model can override it. Every call site passes the same arguments, so the trace shows the same list.
"""

from datetime import timedelta

from backend.conflicts.claims import active_claim, is_suppressed
from backend.core import clock
from backend.core.db import Db
from backend.orchestrator.defs import CH_INTEG, CH_NAME, D, H
from backend.orchestrator.repo import campaign, prospect, rep_for

D_TD = timedelta(milliseconds=D)

REASONS = {
    "kill_switch": "The global kill switch is on",
    "campaign_not_live": "The campaign is a Draft",
    "campaign_paused": "The campaign is Paused",
    "agent_paused": "The Writer agent is off for this campaign",
    "channel_paused": "The channel is off",
    "suppressed": "The prospect is on the suppression list",
    "claimed_by_other_campaign": "Another campaign holds the claim",
    "frequency_cap": "Contacted too recently",
    "no_rep_available": "No active rep",
    "daily_cap": "Daily cap reached",
    "approval_rule": "Campaign rule requires approval",
}


def _rel(ms: int, now_ms: int) -> str:
    s = abs(now_ms - ms) / 1000
    if s < 3600:
        return f"{round(s / 60)} min ago"
    if s < 86400:
        return f"{round(s / 3600)} h ago"
    return f"{round(s / 86400)} d ago"


def sent_today(db: Db, campaign_id: str | None, channel: str | None = None) -> int:
    day_start = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
    sql = "select count(*) as n from messages where direction = 'out' and status = 'sent' and not is_ack and created_at >= %s and created_at < %s"
    params: list = [day_start, day_start + D_TD]
    if campaign_id:
        sql += " and campaign_id = %s"
        params.append(campaign_id)
    if channel:
        sql += " and channel = %s"
        params.append(channel)
    return db.q1(sql, params)["n"]


def evaluate(db: Db, e: dict, ch: str, *, ack: bool = False, reply: bool = False, pricing: bool = False, approved: bool = False, same_day: bool = False) -> dict:
    c = campaign(db, e["campaign_id"])
    p = prospect(db, e["prospect_id"])
    rep = rep_for(db, e, c)
    gs = db.q1("select * from global_settings where id = 1")
    now = clock.now()
    now_ms = clock.ms(now)
    cks: list[dict] = []
    state = {"dec": "allow", "reason": "", "until": None}

    def add(n: int, code: str, ok: bool, note: str, res: str = "defer", reason: str | None = None) -> None:
        cks.append({"n": n, "code": code, "ok": ok, "note": note})
        if not ok and state["dec"] == "allow":
            state["dec"], state["reason"] = res, reason or code

    kill = gs["kill_switch"]
    kill_note = f"Kill switch active since {gs['kill_at']:%H:%M}" if kill and gs["kill_at"] else ("Kill switch active" if kill else "Kill switch off")
    add(1, "kill_switch", not kill, kill_note, "hold")
    live = c["status"] == "live"
    if live:
        add(2, "campaign_live", True, "Campaign is Live")
    elif c["status"] == "paused":
        add(2, "campaign_live", False, "campaign_paused: the campaign is Paused", "hold", "campaign_paused")
    else:
        add(2, "campaign_live", False, f"campaign_not_live: the campaign is {'a Draft' if c['status'] == 'draft' else c['status'].capitalize()}", "block", "campaign_not_live")
    writer_on = c["agents"].get("Writer", False)
    add(3, "agent_enabled", writer_on, "Writer is on" if writer_on else "Writer is paused for this campaign", "hold", "agent_paused")
    integ = db.q1("select paused from integrations where key = %s", (CH_INTEG[ch],))
    ch_on = bool(c["channels"].get(ch)) and not (integ and integ["paused"])
    add(4, "channel_enabled", ch_on, f"{CH_NAME[ch]} is on" if ch_on else f"{CH_NAME[ch]} is paused for this campaign", "replan", "channel_paused")
    supp = is_suppressed(db, p)
    add(5, "suppression", ack or not supp, "Opt-out confirmation is exempt" if ack else ("On the suppression list" if supp else "Not suppressed"), "block", "suppressed")
    claim = active_claim(db, p["id"])
    holds = claim is None or claim["campaign_id"] == e["campaign_id"]
    add(6, "claim", ack or holds, "This campaign holds the claim" if holds else f"{claim['campaign_id']} holds the claim", "defer", "claimed_by_other_campaign")

    last = db.q1(
        "select max(created_at) as t from messages where prospect_id = %s and direction = 'out' and status = 'sent' and not is_reply and not is_ack",
        (p["id"],),
    )
    last_ms = clock.ms(last["t"]) if last and last["t"] else 0
    recent = db.q1(
        "select count(*) as n from messages where prospect_id = %s and direction = 'out' and status = 'sent' and not is_reply and created_at > %s",
        (p["id"], now - 14 * D_TD),
    )["n"]
    window = gs["frequency_window_hours"] * H
    freq_ok = reply or same_day or ((not last_ms or now_ms - last_ms >= window) and recent < 4)
    if not freq_ok and state["dec"] == "allow":
        state["until"] = last_ms + window
    if reply:
        note = "Reply to an inbound message, exempt"
    elif same_day:
        note = "Same opening touch as an earlier channel"
    elif freq_ok:
        note = "Last touch " + (_rel(last_ms, now_ms) if last_ms else "never")
    else:
        note = "4 touches in 14 days" if recent >= 4 else f"Last touch {_rel(last_ms, now_ms)}, {gs['frequency_window_hours']} hours required"
    add(7, "frequency_cap", freq_ok, note, "defer")

    if not rep["active"]:
        rep_ok, rep_reason, rep_note = False, "no_rep_available", f"no_rep_available: {rep['name']} is offboarded"
    else:
        used = _rep_sent_today(db, rep["id"])
        rep_ok = rep["rep_limit"] == 0 or used < rep["rep_limit"]
        rep_reason, rep_note = "daily_cap", (f"{rep['name']} has quota and hours" if rep_ok else "Daily limit reached")
    add(8, "rep_quota", rep_ok, rep_note, "defer", rep_reason)

    total_today = sent_today(db, c["id"])
    ch_limit = c["ch_limit"].get(ch, 0)
    cap_ok = c["daily_send_cap"] > 0 and total_today < c["daily_send_cap"] and (not ch_limit or sent_today(db, c["id"], ch) < ch_limit)
    if cap_ok:
        cap_note = f"{total_today} of {c['daily_send_cap']} sent today"
    elif c["daily_send_cap"] == 0:
        cap_note = "Daily cap is 0 (Draft)"
    else:
        cap_note = "Daily cap reached"
    add(9, "daily_cap", cap_ok, cap_note, "defer")

    first_touch = not db.q1(
        "select 1 as x from messages where enrollment_id = %s and direction = 'out' and not is_reply and status = 'sent' limit 1", (e["id"],)
    )
    appr = c["appr"]
    assisted = ch == "linkedin" and (db.q1("select mode from integrations where key = 'linkedin'") or {}).get("mode") == "live"
    need = not approved and (
        assisted
        or bool(appr.get("all"))
        or (ch == "voice" and appr.get("voice"))
        or (appr.get("first") and first_touch and not reply)
        or (reply and appr.get("reply") and pricing)
    )
    if need and state["dec"] == "allow":
        state["dec"], state["reason"] = "needs_approval", "approval_rule"
    cks.append({"n": 10, "code": "approval_rule", "ok": not need, "note": ("A person sends LinkedIn notes from their own account" if assisted else "Campaign rule requires manager approval") if need else "No approval needed"})
    return {"dec": state["dec"], "reason": state["reason"], "until": state["until"], "cks": cks}


def lock_quota(db: Db, e: dict) -> None:
    """Serialize the quota checks (checks 8 and 9) with the send that follows them, always in the order rep then campaign,
    so parallel workers cannot each see room for the same last slot."""
    c = campaign(db, e["campaign_id"])
    rep = rep_for(db, e, c)
    if rep["id"]:
        db.lock("rep:" + rep["id"])
    db.lock("cap:" + c["id"])


def _rep_sent_today(db: Db, rep_id: str) -> int:
    day_start = clock.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.q1(
        """select count(*) as n from messages m join rep_assignments a on a.campaign_id = m.campaign_id and a.rep_id = %s and a.active
           where m.direction = 'out' and m.status = 'sent' and m.created_at >= %s and m.created_at < %s""",
        (rep_id, day_start, day_start + D_TD),
    )["n"]

