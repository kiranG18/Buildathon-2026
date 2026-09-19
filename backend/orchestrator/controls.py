"""The four stop levels (campaign, agent, channel, global kill switch), replanning and the demo clock.

Pausing writes exactly one row. The worker's claim query joins each job to its own campaign, so pausing A can never stop B or C.
"""

from backend.core import clock
from backend.core.db import Db, J
from backend.core.errors import NotFound, StateConflict
from backend.orchestrator.defs import AGENTS, CH_INTEG, CH_NAME, CHANNELS
from backend.orchestrator.handlers import allowed_channels
from backend.orchestrator.repo import act, campaign, enrollment, prospect


def held_count(db: Db, campaign_id: str | None = None) -> int:
    kill = db.q1("select kill_switch from global_settings where id = 1")["kill_switch"]
    sql = """select count(*) as n from jobs j join campaigns c on c.id = j.campaign_id
             left join campaign_agents a on a.campaign_id = j.campaign_id and a.agent_key = j.agent
             where j.status = 'queued' and (%s or c.status <> 'live' or coalesce(a.enabled, true) = false)"""
    params: list = [kill]
    if campaign_id:
        sql += " and j.campaign_id = %s"
        params.append(campaign_id)
    return db.q1(sql, params)["n"]


def pause_campaign(db: Db, campaign_id: str, by: dict, reason: str | None = None) -> dict:
    c = campaign(db, campaign_id)
    if c["status"] != "live":
        raise StateConflict(f"Only a Live campaign can be paused. This one is {c['status']}", code="not_live")
    now = clock.now()
    db.x("update campaigns set status = 'paused', paused_by = %s, paused_at = %s where id = %s", (by["name"], now, campaign_id))
    held = held_count(db, campaign_id)
    db.x("update campaigns set paused_held = %s where id = %s", (held, campaign_id))
    act(db, None, "pause", f"{by['name']} paused {c['name']}. {held} jobs held" + (f" ({reason})" if reason else ""), cid=campaign_id, agent="Manager")
    return {"status": "paused", "held_jobs": held, "paused_at": clock.ms(now), "paused_by": by["name"]}


def resume_campaign(db: Db, campaign_id: str, by: dict) -> dict:
    c = campaign(db, campaign_id)
    if c["status"] != "paused":
        raise StateConflict(f"Only a Paused campaign can resume. This one is {c['status']}", code="not_paused")
    held = held_count(db, campaign_id)
    db.x("update campaigns set status = 'live', paused_by = null where id = %s", (campaign_id,))
    act(db, None, "resume", f"{by['name']} resumed {c['name']}", cid=campaign_id, agent="Manager")
    return {"status": "live", "requeued_jobs": held}


def set_kill(db: Db, on: bool, by: dict, reason: str | None = None) -> dict:
    now = clock.now()
    if on:
        db.x("update global_settings set kill_switch = true, kill_at = %s, kill_by = %s where id = 1", (now, by["name"]))
        act(db, None, "kill", f"Kill switch on by {by['name']}. All outreach halted", agent="Manager")
    else:
        db.x("update global_settings set kill_switch = false, kill_at = null, kill_by = null where id = 1")
        act(db, None, "kill", f"Platform resumed by {by['name']}", agent="Manager")
    row = db.q1("select kill_switch, kill_at, kill_by from global_settings where id = 1")
    return {"active": row["kill_switch"], "set_by": row["kill_by"], "set_at": clock.ms(row["kill_at"])}


def toggle_agent(db: Db, campaign_id: str, agent: str, by: dict, enabled: bool | None = None, provider: str | None = None) -> dict:
    if agent not in AGENTS:
        raise NotFound(f"Unknown agent {agent}")
    c = campaign(db, campaign_id)
    on = (not c["agents"].get(agent, True)) if enabled is None else enabled
    db.x("update campaign_agents set enabled = %s, provider = coalesce(%s, provider) where campaign_id = %s and agent_key = %s", (on, provider, campaign_id, agent))
    act(db, None, "agent", f"{by['name']} turned {agent} {'on' if on else 'off'} for {c['name']}", cid=campaign_id, agent="Manager")
    return {"agent": agent, "enabled": on}


def toggle_channel(db: Db, campaign_id: str, channel: str, by: dict, enabled: bool | None = None, daily_limit: int | None = None) -> dict:
    if channel not in CHANNELS:
        raise NotFound(f"Unknown channel {channel}")
    c = campaign(db, campaign_id)
    on = (not c["channels"].get(channel, False)) if enabled is None else enabled
    db.x("update channel_settings set enabled = %s, daily_limit = coalesce(%s, daily_limit) where campaign_id = %s and channel = %s", (on, daily_limit, campaign_id, channel))
    if daily_limit is not None:
        limits = {**c["ch_limit"], channel: daily_limit}
        db.x("update campaigns set ch_limit = %s where id = %s", (J(limits), campaign_id))
    act(db, None, "channel", f"{by['name']} turned {CH_NAME[channel]} {'on' if on else 'off'} for {c['name']}", cid=campaign_id, agent="Manager")
    replanned = replan(db, campaign_id, channel) if (not on and c["status"] != "draft") else 0
    return {"channel": channel, "enabled": on, "replanned": replanned}


def set_integration_paused(db: Db, key: str, paused: bool, by: dict) -> int:
    row = db.q1("select * from integrations where key = %s", (key,))
    if not row:
        raise NotFound(f"Unknown integration {key}")
    db.x("update integrations set paused = %s where key = %s", (paused, key))
    act(db, None, "channel", f"{by['name']} {'paused' if paused else 'resumed'} {row['name']} for every campaign", agent="Manager")
    n = 0
    ch = next((c for c, k in CH_INTEG.items() if k == key), None)
    if paused and ch:
        for c in db.q("select id from campaigns where status in ('live', 'paused')"):
            n += replan(db, c["id"], ch)
    return n


def replan(db: Db, campaign_id: str, ch: str) -> int:
    """A channel went off: pending touches on it move to email (or are skipped) with a written reason. One feed event for the campaign."""
    c = campaign(db, campaign_id)
    n = 0
    now = clock.ms(clock.now())
    for row in db.q("select id from enrollments where campaign_id = %s and state in ('qualified', 'contacted', 'awaiting_approval') and jsonb_array_length(plan) > 0", (campaign_id,)):
        e = enrollment(db, row["id"])
        plan = e["plan"]
        old = [f"{CH_NAME[s['ch']]} d{s['day']} {s['purpose']}" for s in plan if s["status"] == "pending"]
        changed = False
        can_email = "email" in allowed_channels(db, e, c)
        for s in plan:
            if s["status"] == "pending" and s["ch"] == ch:
                if can_email:
                    s.update(oldCh=ch, ch="email", reason=f"{CH_NAME[ch]} is off, so the day-{s['day']} touch moved to email", replanned=True)
                    if s["purpose"] in ("connect", "message"):
                        s["purpose"] = "nudge"
                else:
                    s.update(status="skipped", reason=f"{CH_NAME[ch]} is off and no other channel is allowed")
                changed = True
        if changed:
            n += 1
            new = [f"{CH_NAME[s['ch']]} d{s['day']} {s['purpose']}" for s in plan if s["status"] == "pending"]
            hist = [*e["plan_hist"], {"t": now, "old": old, "now": new, "why": f"{CH_NAME[ch]} turned off for {c['name']}"}]
            db.x("update enrollments set plan = %s, plan_hist = %s where id = %s", (J(plan), J(hist), e["id"]))
            p = prospect(db, e["prospect_id"])
            act(db, e, "replan", f"Replanned {p['full_name']}: {CH_NAME[ch]} off, touch moved to email", agent="Sequencer", quiet=True)
    if n:
        act(db, None, "replan", f"Replanned {n} prospect{'' if n == 1 else 's'}: {CH_NAME[ch]} paused, day-3 touch moved to email", cid=campaign_id, agent="Sequencer")
    return n


def advance_clock(db: Db, hours: float) -> dict:
    db.x("update global_settings set demo_clock_offset_hours = demo_clock_offset_hours + %s where id = 1", (hours,))
    clock.invalidate()
    row = db.q1("select demo_clock_offset_hours as h from global_settings where id = 1")
    return {"offset_hours": row["h"]}
