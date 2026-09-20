"""Prospect discovery and CSV import. Discovery calls Apollo.io for real people matching the campaign's ICP when
APOLLO_API_KEY is set (backend/integrations/apollo.py). Without a key, or when Apollo returns nothing usable, it
falls back to the demo lead source (seed/static.json) - the same fallback pattern used for the LLM and embeddings
providers elsewhere in this codebase."""

import random
import re

from agents.util import first as first_name
from agents.util import js_hash, slug
from backend.core import clock
from backend.core.config import get_settings
from backend.core.db import Db, J
from backend.core.errors import StateConflict
from backend.core.logging import log
from backend.integrations import apollo, hunter
from backend.orchestrator.defs import static, tk
from backend.orchestrator.repo import act, campaign, enqueue, new_enrollment

_STOP_KW = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "with", "at", "by"}

FN_US = "Alex Jordan Casey Morgan Riley Taylor Devon Jamie Elena Noah Grace Owen Maya Ethan Chloe Isaac Nora Caleb Ruth Felix Tessa Gabriel Lena Warren Iris Hugo Camille Reid Naomi Jonas Vera Miles Alma Silas Paige Rohan Delia Kenji Yara Bram Selma Tobias Wren Emmett Carmen Dario".split()
LN_US = "Abbott Barnes Castillo Donnelly Everhart Fitch Grady Holloway Ibarra Jennings Kessler Lindgren Maddox Nakamura Ortega Pruitt Quinn Ramsey Sutter Talbot Underhill Vasquez Whitlock Yoon Zeller Ashby Brandt Corliss Dunmore Espinoza Faraday Gallagher Hartwell Iverson Kowalski Lockhart Mercer Novak Okoye Prescott".split()
FN_IN = "Aditya Ananya Arvind Bhavna Chetan Deepa Gaurav Harini Ishaan Jaya Karthik Lakshmi Manoj Neha Omkar Padma Rahul Sanjana Tarun Uma Vivek Yamini Ashwin Bharat Charu Devika Esha Farhan Gopal Hema Imran Jyoti Kabir Lavanya Mohan Nandini Pranav Radhika Suresh Trisha".split()
LN_IN = "Sharma Kulkarni Reddy Iyengar Banerjee Patil Naidu Desai Chawla Bhatia Joshi Kapoor Rao Srinivasan Ghosh Pillai Mehta Sethi Varma Nambiar Tiwari Gupta Krishnan Bose Thakur Menon Hegde Shetty Agarwal Chatterjee".split()
TITLES = {"C1": ["CTO", "VP Engineering", "Head of Platform", "VP Platform"], "C2": ["CIO", "CTO", "Head of Digital", "Chief Digital Officer"],
          "C3": ["Co-founder and CEO", "Founder", "Head of Product", "Co-founder"]}


def _pool(key: str) -> dict[str, dict]:
    out = {}
    for line in static()["POOL"][key].split("\n"):
        n, ind, staff, stage, city = line.split("|")
        out[n] = {"name": n, "ind": ind, "staff": int(staff), "stage": stage, "city": city}
    return out


def _tz(city: str, indian: bool) -> str:
    if indian:
        return "IST"
    if re.search(r"Seattle|Portland|San|Oakland|Los Angeles|Vancouver", city):
        return "PT"
    if re.search(r"Denver|Salt Lake|Phoenix", city):
        return "MT"
    if re.search(r"Austin|Dallas|Chicago|Houston|Nashville|Minneapolis|Memphis|Kansas|Indianapolis", city):
        return "CT"
    return "ET"


def _fact(fid: str, company: str, text: str, src: str, conf: str) -> dict:
    return {"id": fid, "text": text, "src": src, "conf": conf, "url": f"/demo-sources/{slug(company)}/{src}"}


def _fact_real(fid: str, text: str, src: str, conf: str, url: str) -> dict:
    """A fact whose source is a real URL (Apollo-sourced), not a fabricated /demo-sources/ page."""
    return {"id": fid, "text": text, "src": src, "conf": conf, "url": url}


def _rich(db: Db, p: dict, key: str, r: random.Random) -> list[dict]:
    co, out = p["company"], []

    def add(text: str, src: str, conf: str) -> None:
        out.append(_fact(db.nid("F"), co, text, src, conf))

    if key == "C1":
        add(f"{co} posted {r.choice(['two', 'three', 'four', 'five'])} platform or internal-tools engineering roles this month.", "careers", "High")
        if r.random() < 0.6:
            add(f"{co} engineering blog describes internal tools built on {r.choice(['a legacy admin stack', 'spreadsheets and cron jobs', 'a custom back office', 'low-code screens'])}.", "blog", "Medium")
        if r.random() < 0.6:
            add(f"{co} published public API documentation for its {p['ind'].lower().replace(' saas', '')} customers.", "docs", "High")
        if not any(o["src"] != "careers" for o in out):
            add(f"{co} engineering blog describes internal tools built on a custom back office.", "blog", "Medium")
    elif key == "C2":
        add(f"{co} is regulated by {'IRDAI' if 'Insurer' in p['ind'] else 'RBI'} and has about {p['staff']:,} staff.", "rbi", "High")
        add(f"{co} announced a digital transformation programme in {r.choice(['Q1', 'Q2', 'Q3'])} 2026.", "news", "Medium")
        add(f"{co} annual report mentions data localisation obligations.", "annual", "Medium")
    elif key == "C3":
        add(f"{co} ships a {p['ind'].lower()} product with live voice calls.", "product", "High")
        add(f"{co} is hiring {r.choice(['an ML engineer', 'a speech engineer', 'a voice infrastructure engineer'])}.", "careers", "High")
        add(f"{p['first_name']} posts about {r.choice(['voice UX', 'call quality', 'agent latency', 'QA workflows'])} on LinkedIn most weeks.", "linkedin", "Medium")
    return out


def make_prospect(db: Db, name: str, title: str, company: str, key: str, r: random.Random, email: str = "", phone: str = "", linkedin: str = "") -> dict:
    """Create the prospect (and company) or return the existing record. Matching is on lowercased email, so overlap across campaigns is detectable."""
    pid = slug(name)
    existing = db.q1("select id from prospects where id = %s", (pid,))
    if existing:
        return {"id": pid}
    comp = _pool(key).get(company) or next((v for k in ("C1", "C2", "C3") for n, v in _pool(k).items() if n == company), None) or {"name": company, "ind": "", "staff": 100, "stage": "", "city": "Austin"}
    indian = key == "C2"
    intl = bool(re.search(r"Singapore|Dubai", comp["city"]))
    region = "IN" if indian and not intl else ("INTL" if intl else "US")
    local, _, domain = get_settings().seed_inbox_base.partition("@")
    email = email.strip().lower() or f"{local}+{slug(name).replace('-', '.')}@{domain or 'gmail.com'}"
    phone = phone.strip() or (f"+91 98{10000000 + js_hash(pid) % 89999999}" if indian else f"+1 (415) 555-01{js_hash(pid) % 100:02d}")
    cid = slug(company) + ".com"
    db.x("insert into companies (id, name, domain, industry, staff, stage, city) values (%s,%s,%s,%s,%s,%s,%s) on conflict (id) do nothing",
         (cid, company, cid, comp["ind"], comp["staff"], comp["stage"], comp["city"]))
    p = {"first_name": first_name(name), "company": company, "ind": comp["ind"], "staff": comp["staff"]}
    base = (f"{company} has about {comp['staff']:,} staff and operates as a {comp['ind'].lower()}." if indian
            else f"{company} has {comp['staff']} staff{' and a ' + comp['stage'] + ' round' if comp['stage'] and comp['stage'] != 'n/a' else ''}.")
    facts = [_fact(db.nid("F"), company, base, "about", "High")]
    rich = _rich(db, p, key, r)
    db.x(
        """insert into prospects (id, company_id, full_name, first_name, title, email, phone, linkedin_url, region, timezone, facts, rich)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (pid, cid, name, first_name(name), title, email, phone, linkedin.strip() or f"linkedin.com/in/{slug(name)}", region, _tz(comp["city"], indian), J(facts), J(rich)),
    )
    return {"id": pid}


def _keywords(c: dict) -> list[str]:
    text = " ".join(x for x in (c["icp"], c["personas"], c["signals"]) if x)
    toks = [t for t in re.findall(r"[A-Za-z][A-Za-z0-9+.-]{2,}", text) if t.lower() not in _STOP_KW]
    seen: set[str] = set()
    out = []
    for t in toks:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:8]


def _make_prospect_from_apollo(db: Db, person: apollo.ApolloPerson, email: str, key: str) -> dict:
    """Insert a real company and prospect from an Apollo hit. Facts carry the org's or the person's real URL."""
    org = person.org
    indian = key == "C2" or "india" in (org.city or "").lower()
    cid = org.domain or (slug(org.name) + ".com")
    db.x(
        "insert into companies (id, name, domain, industry, staff, stage, city) values (%s,%s,%s,%s,%s,%s,%s) on conflict (id) do nothing",
        (cid, org.name, org.domain or cid, org.industry, org.staff, "", org.city),
    )
    site = org.website_url or (f"https://{org.domain}" if org.domain else "")
    about = f"{org.name} is a {org.industry.lower()} company with about {org.staff:,} staff." if org.industry and org.staff else (
        f"{org.name} has about {org.staff:,} staff." if org.staff else f"{org.name}: {org.description or 'company details from Apollo'}."
    )
    facts = [_fact_real(db.nid("F"), about.strip(), "about", "High" if org.staff else "Medium", site)]
    if org.description and org.description not in about:
        facts.append(_fact_real(db.nid("F"), org.description, "about", "Medium", site))
    rich = []
    if person.linkedin_url:
        rich.append(_fact_real(db.nid("F"), f"{person.name} is listed as {person.title or 'a contact'} at {org.name} on LinkedIn.", "linkedin", "High", person.linkedin_url))
    pid = slug(person.name)
    db.x(
        """insert into prospects (id, company_id, full_name, first_name, title, email, phone, linkedin_url, region, timezone, facts, rich)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (pid, cid, person.name, first_name(person.name), person.title, email.strip().lower(), person.phone or "", person.linkedin_url or "",
         "IN" if indian else "US", _tz(org.city, indian), J(facts), J(rich)),
    )
    return {"id": pid}


def _discover_live(db: Db, c: dict, campaign_id: str, key: str, n: int) -> list[dict]:
    try:
        people = apollo.search_people(list(c["roles"] or TITLES.get(key, [])), list(c["geo_list"] or []), _keywords(c), n)
    except apollo.ApolloUnavailable:
        return []
    made = []
    for person in people:
        if len(made) >= n:
            break
        if not person.name:
            continue
        email = person.email
        if person.email_locked or not email:
            try:
                revealed = apollo.reveal_contact(person.apollo_id) if person.apollo_id else None
            except apollo.ApolloUnavailable:
                revealed = None
            if not revealed or not revealed.email:
                continue
            person, email = revealed, revealed.email
        if db.q1("select 1 as x from prospects where id = %s", (slug(person.name),)) or db.q1("select 1 as x from prospects where lower(email) = lower(%s)", (email,)):
            continue
        pr = _make_prospect_from_apollo(db, person, email, key)
        e = new_enrollment(db, pr["id"], campaign_id)
        act(db, e, "discover", f"Discovered {person.name}, {person.title or 'contact'} at {person.org.name} via Apollo", agent="Researcher")
        if c["status"] != "draft":
            enqueue(db, e, "research")
        made.append(e)
    return made


def _key_for(c: dict) -> str:
    t = tk(c)
    if t in ("C2", "C3"):
        return t
    return "C2" if "India" in (c["geo_list"] or []) else "C1"


def _name(key: str, r: random.Random, db: Db) -> str:
    for _ in range(60):
        n = (r.choice(FN_IN) + " " + r.choice(LN_IN)) if key == "C2" else (r.choice(FN_US) + " " + r.choice(LN_US))
        if not db.q1("select 1 as x from prospects where id = %s", (slug(n),)):
            return n
    return "Guest " + db.nid("")


def discover(db: Db, campaign_id: str, n: int, by: dict | None = None) -> list[dict]:
    c = campaign(db, campaign_id)
    if c["status"] in ("completed", "archived"):
        raise StateConflict("This campaign is closed")
    key = _key_for(c)
    if get_settings().apollo_api_key:
        made = _discover_live(db, c, campaign_id, key, n)
        if made:
            return made
        log().warning("apollo discovery found nothing usable, falling back to the seeded pool", extra={"event": "apollo_fallback", "campaign_id": campaign_id})
    r = random.Random(js_hash(campaign_id) + db.q1("select count(*) as n from enrollments where campaign_id = %s", (campaign_id,))["n"] * 13)
    made = []
    for _ in range(n):
        used = {row["name"] for row in db.q("select co.name from enrollments e join prospects p on p.id = e.prospect_id join companies co on co.id = p.company_id where e.campaign_id = %s", (campaign_id,))}
        free = [x for x in static()["RESERVE"].get(key, []) if x not in used]
        if not free:
            break
        name = _name(key, r, db)
        title = r.choice(c["roles"] or TITLES.get(key, ["Head of Digital"]))
        pr = make_prospect(db, name, title, free[0], key, r)
        e = new_enrollment(db, pr["id"], campaign_id)
        act(db, e, "discover", f"Discovered {name}, {title} at {free[0]}", agent="Researcher")
        if c["status"] != "draft":
            enqueue(db, e, "research")
        made.append(e)
    return made


def import_linkedin(db: Db, campaign_id: str, company: str, domain: str, people: list[dict], by: dict | None = None) -> dict:
    """Real people found by scripts/linkedin_find_employees.js (run locally, against a real logged-in
    LinkedIn session - see MANUAL_ACTIONS.md MA-14). Each entry is {name, title, profile_url}.

    Company facts come from Apollo (organizations/enrich, works on the free plan) when a domain is given
    and a key is configured. Each person's email comes from Hunter's Email Finder when a domain and a
    Hunter key are configured; otherwise the prospect gets the same clearly-labelled sandbox placeholder
    address used everywhere else in this codebase - never a guessed one, so it can never look like a real,
    verified email it isn't, and it never matches ALLOWED_RECIPIENTS by accident."""
    c = campaign(db, campaign_id)
    if c["status"] in ("completed", "archived"):
        raise StateConflict("This campaign is closed")
    key = _key_for(c)
    org = None
    if domain and get_settings().apollo_api_key:
        try:
            org = apollo.enrich_domain(domain)["company"]
        except apollo.ApolloUnavailable:
            org = None
    cid = domain or (org.domain if org else "") or (slug(company) + ".com")
    db.x(
        "insert into companies (id, name, domain, industry, staff, stage, city) values (%s,%s,%s,%s,%s,%s,%s) on conflict (id) do nothing",
        (cid, (org.name if org else company) or company, domain or cid, org.industry if org else "", org.staff if org else 0, "", org.city if org else ""),
    )
    site = (org.website_url if org else "") or (f"https://{domain}" if domain else "")
    created, skipped = [], 0
    for person in people:
        name = (person.get("name") or "").strip()
        profile_url = (person.get("profile_url") or "").strip()
        title = (person.get("title") or "").strip()
        if not name or not profile_url:
            skipped += 1
            continue
        pid = slug(name)
        if db.q1("select 1 as x from prospects where id = %s", (pid,)) or db.q1("select 1 as x from prospects where linkedin_url = %s", (profile_url,)):
            skipped += 1
            continue
        email, email_real = "", False
        if domain and get_settings().hunter_api_key:
            parts = name.split(" ", 1)
            try:
                found = hunter.find_email(parts[0], parts[1] if len(parts) > 1 else "", domain)
                if found:
                    email, email_real = found.email, True
            except hunter.HunterUnavailable:
                pass
        if not email:
            local, _, mail_domain = get_settings().seed_inbox_base.partition("@")
            email = f"{local}+{slug(name).replace('-', '.')}@{mail_domain or 'gmail.com'}"
        facts = [_fact_real(db.nid("F"), f"{name} is listed as {title or 'a contact'} at {company} on LinkedIn.", "linkedin", "High", profile_url)]
        if org and org.description:
            facts.append(_fact_real(db.nid("F"), org.description, "about", "Medium", site))
        rich = [] if email_real else [_fact_real(db.nid("F"), "Email not verified by Hunter - sandbox address in use.", "about", "Low", profile_url)]
        db.x(
            """insert into prospects (id, company_id, full_name, first_name, title, email, phone, linkedin_url, region, timezone, facts, rich)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (pid, cid, name, first_name(name), title, email.strip().lower(), "", profile_url, "IN" if key == "C2" else "US", _tz(org.city if org else "", key == "C2"), J(facts), J(rich)),
        )
        e = new_enrollment(db, pid, campaign_id)
        act(db, e, "discover", f"Found {name}, {title or 'contact'} at {company} on LinkedIn" + (" (email verified by Hunter)" if email_real else " (email unverified, sandbox address)"), agent="Researcher")
        if c["status"] != "draft":
            enqueue(db, e, "research")
        created.append(e)
    return {"created": len(created), "skipped": skipped, "enrolled_ids": [e["id"] for e in created]}


def import_rows(db: Db, campaign_id: str, rows: list[list[str]], by: dict) -> dict:
    c = campaign(db, campaign_id)
    key = _key_for(c)
    r = random.Random(js_hash(campaign_id) + 7)
    created = deduped = 0
    for name, title, company, email, phone, linkedin in ((x[0], x[1], x[2], *(x[3:6] + [""] * (3 - len(x[3:6])))) for x in rows if len(x) >= 3 and x[0]):
        pr = make_prospect(db, name, title, company, key, r, email, phone, linkedin)
        if db.q1("select 1 as x from enrollments where campaign_id = %s and prospect_id = %s", (campaign_id, pr["id"])):
            deduped += 1
            continue
        e = new_enrollment(db, pr["id"], campaign_id)
        act(db, e, "discover", f"Imported {name}, {title} at {company}", agent="Manager")
        if c["status"] != "draft":
            enqueue(db, e, "research")
        created += 1
    return {"created": created, "deduped": deduped, "enrolled": created}


__all__ = ["discover", "import_rows", "import_linkedin", "clock"]
