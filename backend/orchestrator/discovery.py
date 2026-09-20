"""Prospect discovery and CSV import. Live scraping is out of scope, so discovery draws from the demo lead source (seed/static.json)."""

import random
import re

from agents.util import first as first_name
from agents.util import js_hash, slug
from backend.core import clock
from backend.core.config import get_settings
from backend.core.db import Db, J
from backend.core.errors import StateConflict
from backend.orchestrator.defs import static, tk
from backend.orchestrator.repo import act, campaign, enqueue, new_enrollment

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


__all__ = ["discover", "import_rows", "clock"]
