"""Deterministic agent behaviour. This is the LLM_MODE=fake path and the rule-based fallback used when a model call fails.

The Writer templates depend on the active Writer prompt version: v1 states unsupported claims (which the verifier blocks),
v2 grounds every claim in a fact or a knowledge chunk. That is how prompt versions change behaviour without a live model.
"""

import re

from agents.util import f_d, f_dt, js_hash, slots_for
from agents.util import first as first_name
from backend.orchestrator.defs import CRIT_VALUE, HERO_SCORES, static


def pl(t: str) -> dict:
    return {"t": t}


def cl(t: str, src: str) -> dict:
    return {"t": t, "src": src}


def _fact(p: dict, kind: str) -> dict | None:
    return next((f for f in p["facts"] if f["src"] == kind), None)


def compose(kind: str, *, p: dict, tkey: str, rep_name: str, ver: int, now_ms: float, meeting: dict | None = None, wake_ms: float | None = None) -> dict:
    f, co = p["first_name"], p["company"]
    rf = first_name(rep_name)
    hook_kind = {"C1": "careers", "C2": "news", "C3": "product", "C4": "about"}[tkey]
    hook = _fact(p, hook_kind) or _fact(p, "rbi") or _fact(p, "about") or (p["facts"][0] if p["facts"] else None)
    second = next((x for x in p["facts"] if x is not hook and x["src"] != "about"), None) or next((x for x in p["facts"] if x is not hook), None)
    hooked = [cl(hook["text"], hook["id"])] if hook else [pl(f"{co} looks like a strong fit for what we build.")]
    sl = slots_for(now_ms)
    tz = p["timezone"]
    ch, subject = "email", None
    segs: list[dict]
    if kind == "intro":
        if tkey == "C1":
            if ver == 1:
                segs = [pl(f"Hi {f},\n\nI came across {co} and thought Helix Agents might help. We help engineering teams automate internal workflows with AI agents, and "),
                        cl("customers see big results", "?"), pl(f".\n\nWould you be open to a quick call?\n\n{rf}")]
            else:
                segs = [pl(f"Hi {f},\n\n"), *hooked,
                        pl(" Teams at that stage usually watch the internal-tools backlog grow faster than hiring can clear it.\n\nHelix Agents automates approvals, onboarding and data-sync work with governed AI agents. "),
                        cl("Northbeam cut its internal-tool request backlog by 41% in one quarter.", "K-207"), pl(f"\n\nWorth 20 minutes to see if it fits {co}?\n\n{rf}")]
            subject = f"{co} and the internal-tools backlog"
        elif tkey == "C2":
            if ver == 1:
                segs = [pl(f"Dear {f},\n\nI am writing to introduce Helix Agents, a leading AI platform trusted by many financial institutions. "), cl("We are fully RBI approved.", "?"),
                        pl(f"\n\nMay we schedule a call?\n\nRegards,\n{rep_name}")]
            else:
                segs = [pl(f"Dear {f},\n\n"), *hooked, pl(" We work with regulated lenders and insurers on agent workflows that "),
                        cl("keep customer data in the India region you choose and log every decision for audit.", "K-312"), pl("\n\n"),
                        cl("Tamarai Finance cut loan-document turnaround from 3 days to 9 hours on this basis.", "K-307"),
                        pl(f"\n\nMay I arrange an introduction with our solutions lead, {rep_name}, to discuss a compliance-safe pilot?\n\nRegards,\n{rep_name}")]
            subject = f"{co}: in-region agents with a full audit trail"
        elif tkey == "C3":
            if ver == 1:
                segs = [pl(f"Hi {f},\n\nHope you are well! We are Helix Agents and we would love to help {co} grow with our AI platform. "), cl("Our customers save huge amounts of time.", "?"),
                        pl(f"\n\nFree for a call?\n\n{rf}")]
            else:
                segs = [pl(f"Hey {f},\n\n"), *hooked, pl(" Founder to founder: "), cl("Ringlet now reviews every call instead of 8% after two weeks on Helix agents.", "K-407"),
                        pl(f"\n\nOpen to 15 minutes?\n\n{rf}")]
            subject = f"{co} and call QA"
        else:
            segs = [pl(f"Hi {f},\n\n"), *hooked,
                    pl(f" I would like to review where agents can take on more of the workflow before your renewal.\n\nCould we book 30 minutes for an expansion review?\n\n{rf}")]
            subject = f"{co}: getting more from your Helix seats"
    elif kind == "connect":
        ch = "linkedin"
        if tkey == "C1":
            segs = [pl(f"Hi {f}, I emailed about "), cl(hook["text"].rstrip(".") if hook else co, hook["id"] if hook else "?"), pl(". Connecting here in case LinkedIn is easier.")]
        elif tkey == "C2":
            segs = [pl(f"Dear {f}, "), *hooked, pl(" I lead pilots at Helix Agents for regulated lenders, with "), cl("customer data kept in your India region.", "K-312"), pl(f" Glad to connect. {rf}")]
        else:
            segs = [pl(f"Hey {f}, love what {co} is building. "), *hooked, pl(" Would like to connect.")]
    elif kind == "message":
        ch = "linkedin"
        if tkey == "C2":
            segs = [pl(f"Thank you for connecting, {f}. "), cl("Every agent action, prompt version and approval is logged and exportable.", "K-313"), pl(" I would welcome a short call to walk through it.")]
        else:
            segs = [pl(f"Thanks for connecting, {f}. "), cl("Helix agents cleared 41% of Northbeam's internal-tool backlog in a quarter.", "K-207"), pl(" Happy to share how.")]
    elif kind == "nudge":
        tail = (cl("Helix agents deploy in days, keep an audit trail per call and price per workflow.", "K-412") if tkey == "C3"
                else cl("Helix agents run inside your VPC and log every action, so security review stays short.", "K-002"))
        segs = [pl(f"Hi {f},\n\nOne more angle. "), *([cl(second["text"], second["id"])] if second else [pl(f"{co} may be stretching its platform team.")]), pl(" "), tail,
                pl(f"\n\nWould a two-page summary help?\n\n{rf}")]
        subject = f"Another angle for {co}"
    elif kind == "breakup":
        segs = [pl(f"Hi {f},\n\nI will stop here so I do not clutter your inbox. If the {'call-QA' if tkey == 'C3' else 'internal-tools'} backlog becomes a priority, reply and I will pick it up.\n\n{rf}")]
        subject = f"Closing the loop, {co}"
    elif kind == "call_offer":
        segs = [pl(f"Dear {f},\n\nFurther to my note, I would welcome a short call to walk through the "), cl("audit trail and in-region deployment.", "K-313"),
                pl(f" Would {sl[0]['label'].split(',')[0]} or {sl[1]['label'].split(',')[0]} suit you?\n\nRegards,\n{rep_name}")]
        subject = "A short call on in-region agents"
    elif kind == "sms":
        ch = "sms"
        segs = [pl(f"Hey {f}, {rf} from Helix. Sent you a note by email and LinkedIn about call QA. 15 min this week? Reply STOP to opt out.")]
    elif kind == "slots":
        if sl[0].get("url") and sl[1].get("url"):
            segs = [pl(f"Thanks {f}. {rf} has two slots: {sl[0]['label']} ({sl[0]['url']}) or {sl[1]['label']} ({sl[1]['url']}) ({tz}). Pick a link to book instantly, or reply with the one you prefer.")]
        else:
            segs = [pl(f"Thanks {f}. {rf} has two slots: {sl[0]['label']} or {sl[1]['label']} ({tz}). Reply with the one you prefer and I will send the invite.")]
        subject = "Re: " + co
    elif kind == "confirm":
        m = meeting or sl[0]
        label = m.get("label") or f_dt(m.get("t") or m.get("at"))
        segs = [pl(f"Confirmed. {rf} will meet you on {label} ({tz}). A calendar invite is on its way.")]
        subject = "Confirmed: " + co
    elif kind == "obj_inhouse":
        segs = [pl(f"Fair point, {f}. "), cl("Most teams can build a first agent. The cost sits in governance, audit trails, evals and upkeep.", "K-211"), pl(" "),
                cl("Northbeam's platform team of six shipped its first three agents in nine working days without new headcount.", "K-208"), pl(" Happy to share the two-week pilot outline.")]
        subject = "Re: " + co
    elif kind == "obj_residency":
        segs = [pl(f"Thank you, {f}. "), cl("Customer data stays in the India region you choose, Mumbai or Hyderabad, with no cross-border transfer, and model calls run in region.", "K-312"),
                pl(" "), cl("Every agent action and approval is logged and exportable for audit.", "K-313")]
        subject = "Re: " + co
    elif kind == "obj_competitor":
        segs = [pl(f"Makes sense, {f}. "), cl("Helix agents deploy in days, keep an audit trail per call and price per workflow instead of per seat.", "K-412"), pl(" Happy to compare on setup time and cost per reviewed call.")]
        subject = "Re: " + co
    elif kind == "case_study":
        text, src = {
            "C3": ("Ringlet now reviews every call instead of 8% after two weeks on Helix agents.", "K-407"),
            "C2": ("Tamarai Finance cut loan-document turnaround from 3 days to 9 hours, with every decision logged for audit.", "K-307"),
        }.get(tkey, ("Northbeam cut its internal-tool request backlog from 212 to 125 tickets in one quarter (41%).", "K-207"))
        segs = [pl(f"Sure, {f}. "), cl(text, src), pl(" I will send the two-page write-up with the pilot outline.")]
        subject = "Re: " + co
    elif kind == "pricing_answer":
        segs = [pl(f"Thanks {f}. "), cl("List pricing starts at $1,500 per month for the Additional API tier, per workflow plus usage.", "K-021"), pl(f" Any discount or custom terms go through {rep_name}.")]
        subject = "Re: " + co
    elif kind == "obj_budget":
        segs = [pl(f"Understood, {f}. "), cl("We suggest starting with one workflow. The pilot covers a single team and is priced at list.", "K-212")]
        subject = "Re: " + co
    elif kind == "answer_q":
        segs = [pl(f"Thanks {f}. "), cl("Helix Agents automates approvals, onboarding, data sync and voice tasks under central governance.", "K-001"),
                pl(f" Could you share which workflow is the priority at {co}? {rf} can then map it out on a call.")]
        subject = "Re: " + co
    elif kind == "notnow":
        segs = [pl(f"Understood, {f}. I will check back around {f_d(wake_ms or now_ms + 90 * 86_400_000)}. Nothing is needed from you until then.")]
        subject = "Re: " + co
    elif kind == "unsub":
        segs = [pl(f"Confirmed, {f}. You are unsubscribed and will not hear from Helix again.")]
        subject = "Unsubscribed"
    elif kind == "escalate":
        segs = [pl(f"Thanks {f}. This one needs {rep_name}, who owns commercial and security review on our side. {rf} will reply to you today.")]
        subject = "Re: " + co
    else:
        segs = [pl(str(kind))]
    if ch in ("linkedin", "sms"):
        subject = None
    return {"ch": ch, "subject": subject, "segs": segs, "body": "".join(s["t"] for s in segs), "claims": [s for s in segs if s.get("src")]}


ESC_SUGGEST = {
    "pricing_negotiation": "Hi {f}, thanks for the detail on volume. Discounts and custom terms are set on a call, and list pricing stays at $1,500 per month for the Additional API tier until then. I can do {slot} if that suits you.",
    "security_questionnaire": "Hi {f}, thanks. Our security team shares the SOC 2 Type II report under NDA. I will send the NDA today and route the questionnaire to security.",
    "legal_terms": "Hi {f}, thanks for raising this. I will bring in our legal contact and come back with a named person today.",
    "human_request": "Hi {f}, of course. Are you free for a call {slot}?",
    "hostile_tone": "Hi {f}, apologies for the noise. I have paused all outreach to you and will follow up personally only if you ask.",
}


def classify(text: str) -> dict:
    """Rules first: opt-out, out-of-office and hard escalation triggers cost no model call."""
    t = text.lower()
    rules = [
        (r"unsubscribe|stop emailing|remove me|opt out|do not contact|don't contact", {"cls": "unsubscribe", "rule": "keyword: opt-out"}),
        (r"out of office|on leave|auto-?reply|away until", {"cls": "ooo", "rule": "keyword: out of office"}),
        (r"soc ?2|security questionnaire|pen ?test|vendor risk|infosec", {"cls": "escalate", "sub": "security_questionnaire", "rule": "hard trigger: security questionnaire"}),
        (r"discount|% off|volume pricing|price match|negotiat|cheaper", {"cls": "escalate", "sub": "pricing_negotiation", "rule": "hard trigger: pricing negotiation"}),
        (r"legal|contract|msa|indemn", {"cls": "escalate", "sub": "legal_terms", "rule": "hard trigger: legal terms"}),
        (r"speak to a human|talk to (a )?(person|human|someone)|call me", {"cls": "escalate", "sub": "human_request", "rule": "hard trigger: request for a human"}),
        (r"spam|stop bothering|lawyer|report you", {"cls": "escalate", "sub": "hostile_tone", "rule": "hard trigger: hostile tone"}),
        (r"not now|not this quarter|next quarter|revisit|later this year|maybe in q", {"cls": "not_now", "rule": "keyword: timing"}),
        (r"in-?house|build (this|it) ourselves|building this", {"cls": "objection", "sub": "inhouse", "rule": "LLM: objection, build vs buy"}),
        (r"already use|competitor|using [a-z]+ already", {"cls": "objection", "sub": "competitor", "rule": "LLM: objection, incumbent tool"}),
        (r"data (stay|reside|live)|residency|where does|rbi|localis", {"cls": "objection", "sub": "residency", "rule": "LLM: objection, data residency"}),
        (r"case stud", {"cls": "objection", "sub": "case", "rule": "LLM: asks for a case study"}),
        (r"how much|what does it cost|pricing|price list|what.s the price", {"cls": "objection", "sub": "pricing", "rule": "LLM: pricing question"}),
        (r"budget|too expensive|no money", {"cls": "objection", "sub": "budget", "rule": "LLM: objection, budget"}),
        (r"works for me|works for us|book|confirm|i'?ll take|slot|thursday|tuesday|wednesday|friday|monday", {"cls": "book", "rule": "keyword: slot acceptance"}),
        (r"interested|send details|pilot|tell me more|sounds good|yes|timely|love to", {"cls": "positive", "rule": "LLM: positive intent"}),
    ]
    for pattern, out in rules:
        if re.search(pattern, t):
            return dict(out)
    return {"cls": "question", "rule": "LLM: unclear, ask a question"}


def crit_for(p: dict, tkey: str) -> list[dict]:
    """Judge each ICP criterion from the facts on file. Unknown stays unknown, never a guess."""
    labels = static()["CRIT"][tkey]
    has = lambda k: _fact(p, k)  # noqa: E731
    lc = bool(p.get("thin") or p.get("is_empty"))
    ev = lambda k: (has(k) or {}).get("id")  # noqa: E731
    staff, stage, region, ind = p["staff"], p["stage"], p["region"], p["ind"]
    if tkey == "C1":
        s = [
            ("part" if lc else "met") if 100 <= staff <= 1000 else ("part" if staff >= 50 else "no"),
            ("part" if lc else "met") if re.search(r"Series [BCD]", stage) else ("part" if re.search(r"Series A", stage) else "no"),
            ("met" if has("careers")["conf"] == "High" else "part") if has("careers") else "unk",
            "met" if (has("docs") or has("blog")) else ("part" if has("careers") else "unk"),
            "met" if region == "US" else "no",
        ]
        evs = ["about", "about", "careers", "blog", "about"]
    elif tkey == "C2":
        rej = (p.get("rej") or {}).get("C2", "")
        s = [
            "met" if has("rbi") else ("no" if re.search(r"Not a regulated", rej) else ("part" if re.search(r"NBFC|bank|Insurer|Housing|Payments", ind, re.I) else "unk")),
            ("part" if lc else "met") if staff >= 1000 else "no",
            "part" if has("news") else "unk",
            "part" if has("annual") else "unk",
            "met" if region == "IN" else "no",
        ]
        evs = ["rbi", "about", "news", "annual", "about"]
    elif tkey == "C3":
        s = [
            ("met" if has("product")["conf"] == "High" else "part") if has("product") else "unk",
            ("part" if lc else "met") if staff <= 50 else ("part" if staff <= 150 else "no"),
            ("part" if lc else "met") if re.search(r"Seed|Series A", stage) else ("part" if re.search(r"Series B", stage) else "no"),
            "part" if has("linkedin") else "unk",
            "met" if region == "US" else "no",
        ]
        evs = ["product", "about", "about", "linkedin", "about"]
    else:
        s = ["met", "met", "unk", "part", "met"]
        evs = ["about"] * 5
    return [{"label": lab, "st": st, "ev": ev(k)} for lab, st, k in zip(labels, s, evs, strict=True)]


def score_of(campaign_id: str, prospect_id: str, crit: list[dict]) -> int:
    key = f"{prospect_id}:{campaign_id}"
    if key in HERO_SCORES:
        return HERO_SCORES[key]
    v = round(100 * sum(CRIT_VALUE[x["st"]] for x in crit) / len(crit))
    if v >= 90:
        v = min(99, v - 2 - js_hash(prospect_id + campaign_id) % 12)
    return v


def build_default_plan(tkey: str, allowed: list[str], t0_ms: float) -> list[dict]:
    """The campaign's default sequence, adapted to the channels that are allowed right now."""
    st = static()
    day = 86_400_000
    steps = []
    for s in st["SEQ"][tkey]:
        ch, reason, purpose, status = s["ch"], st["REASON"][s["purpose"]], s["purpose"], "pending"
        if ch not in allowed:
            if ch == "linkedin" and "email" in allowed:
                ch, purpose = "email", ("nudge" if s["purpose"] == "connect" else purpose)
                reason = "LinkedIn is paused, so this touch moves to email"
            else:
                status = "skipped"
                reason = {"email": "Email", "linkedin": "LinkedIn", "sms": "SMS", "voice": "Voice"}[ch] + " is not available for this campaign"
        steps.append({"day": s["day"], "ch": ch, "purpose": purpose, "reason": reason, "status": status, "due": t0_ms + s["day"] * day, "cond": s.get("cond")})
    return steps
