"""Static definitions shared by the orchestrator, agents and policy code."""

import json
from functools import lru_cache
from pathlib import Path

H = 3600 * 1000
D = 24 * H
MIN = 60 * 1000

FIRST_TOUCH_DELAY_MS = 20 * 1000
CHANNELS = ("email", "linkedin", "sms", "voice")
CH_NAME = {"email": "Email", "linkedin": "LinkedIn", "sms": "SMS", "voice": "Voice"}
CH_INTEG = {"email": "gmail", "linkedin": "linkedin", "sms": "twilio", "voice": "voice"}

AGENTS = ("Researcher", "Qualifier", "Sequencer", "Writer", "Responder", "Caller")
ROLES = ("System", "Qualifier", "Researcher", "Strategy", "Follow-up", "Writer", "Responder", "Caller")
AGENT_ROLE = {"Researcher": "Researcher", "Qualifier": "Qualifier", "Sequencer": "Strategy", "Writer": "Writer", "Responder": "Responder", "Caller": "Caller"}
AGENT_META = {
    "Researcher": {"model": "DronaHQ agent, web search + enrichment", "host": "DronaHQ", "cost": 0.012, "dur": 4.1},
    "Qualifier": {"model": "openai/gpt-oss-20b", "host": "Groq", "cost": 0.001, "dur": 0.4},
    "Sequencer": {"model": "openai/gpt-oss-120b", "host": "Groq", "cost": 0.0015, "dur": 0.9},
    "Writer": {"model": "openai/gpt-oss-120b", "host": "Groq", "cost": 0.0018, "dur": 1.2},
    "Responder": {"model": "DronaHQ agent, MCP tools", "host": "DronaHQ", "cost": 0.015, "dur": 2.9},
    "Caller": {"model": "DronaHQ Voice agent", "host": "DronaHQ", "cost": 0.11, "dur": 74},
}
JOB_AGENT = {"research": "Researcher", "qualify": "Qualifier", "plan": "Sequencer", "draft": "Writer", "reply": "Responder", "call": "Caller"}

# enrollment state -> funnel stage index (0 Discovered ... 5 Meeting)
STATE_STAGE = {
    "new": 0, "researched": 1, "rejected": 1, "borderline": 1, "qualified": 2, "awaiting_approval": 2, "awaiting_voice": 2, "deferred": 2,
    "contacted": 3, "replied_pos": 4, "replied_obj": 4, "replied_notnow": 4, "escalated": 4, "opted_out": 4, "meeting": 5, "stopped": 1,
}
STAGES = ("Discovered", "Researched", "Qualified", "Contacted", "Engaged", "Meeting")
ACTIVE_STATES = ("qualified", "contacted")
CRIT_VALUE = {"met": 1.0, "part": 0.55, "unk": 0.3, "no": 0.0}
ESC_LABEL = {
    "pricing_negotiation": "Pricing negotiation", "security_questionnaire": "Security questionnaire", "legal_terms": "Legal terms",
    "human_request": "Asked for a human", "hostile_tone": "Hostile tone",
}
HERO_SCORES = {"sam-okafor:C1": 82, "sam-okafor:C3": 63, "aaron-feld:C1": 78, "aaron-feld:C3": 85}
KB_ICP = {"C1": "K-101", "C2": "K-301", "C3": "K-401", "C4": "K-501"}
KB_ICP2 = {"C1": "K-102", "C2": "K-302", "C3": "K-402", "C4": "K-511"}
KB_PLAY = {"C1": "K-231", "C2": "K-331", "C3": "K-441", "C4": "K-511"}


@lru_cache
def static() -> dict:
    return json.loads((Path(__file__).resolve().parents[2] / "seed" / "static.json").read_text(encoding="utf-8"))


def tk(campaign: dict) -> str:
    """Template key of a campaign: its own id for seeded ones, the chosen template for user-created ones."""
    return campaign.get("tpl") or campaign["id"]
