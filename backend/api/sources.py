"""Hosted source pages for the demo prospects, and the enrichment tool the DronaHQ Researcher calls.

Fictional companies have no web presence, so every fact keeps a real URL on this API. A judge who clicks an evidence link lands on the page the fact came from.

For a domain not already in this workspace, /tools/enrich proxies Apollo.io when APOLLO_API_KEY is set, and returns
real facts with real source URLs instead of the seeded pages.

/tools/linkedin-finder.js serves scripts/linkedin_find_employees.js as a real download, and /tools/linkedin-import
receives what it finds. That script needs a real logged-in LinkedIn session, which only exists on someone's own
laptop (see MANUAL_ACTIONS.md MA-14) - this API never automates LinkedIn itself.
"""

import html
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from backend.core.config import get_settings
from backend.core.db import Db
from backend.core.errors import NotFound
from backend.core.security import db_dep, webhook_guard
from backend.integrations import apollo
from backend.orchestrator import discovery

router = APIRouter()
SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "linkedin_find_employees.js"

BODY = {
    "careers": "Open roles: Senior Platform Engineer, Staff Engineer for Internal Tools, Platform Reliability Engineer.",
    "docs": "API reference: authentication, rate limits, webhooks and SDKs for customers.",
    "about": "Company at a glance: team size, funding and headquarters.",
    "blog": "Engineering blog: how the team runs its internal tools today and what slows it down.",
    "rbi": "Regulated entity register: entity category, registered office and licence status.",
    "news": "Press release: the company describes the programme and its planned first phase.",
    "annual": "Annual report, risk section: obligations on data localisation and vendor oversight.",
    "product": "Product page: live voice features, supported channels and customer logos.",
    "linkedin": "Public post by the founder: notes on what the team shipped and learned this week.",
}


def _find(db: Db, path: str) -> tuple[dict, dict] | None:
    for p in db.q("select p.id, p.full_name, p.facts, p.rich, c.name as company, c.city from prospects p join companies c on c.id = p.company_id"):
        for f in [*p["facts"], *p["rich"]]:
            if f["url"] == path:
                return p, f
    return None


@router.get("/demo-sources/{slug}/{src}", response_class=HTMLResponse)
def source_page(slug: str, src: str, db: Db = Depends(db_dep)) -> str:
    hit = _find(db, f"/demo-sources/{slug}/{src}")
    if not hit:
        raise NotFound("No such source page")
    p, f = hit
    e = html.escape
    return (
        f"<!doctype html><html lang='en'><meta charset='utf-8'><title>{e(p['company'])}: {e(src)}</title>"
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:640px;margin:48px auto;padding:0 20px;color:#1f201d}small{color:#5d5e58}</style>"
        f"<h1>{e(p['company'])}</h1><p><small>{e(p['city'])}. Demo source page. Every record in this workspace is fictional.</small></p>"
        f"<p>{e(BODY.get(src, 'Page excerpt.'))}</p><blockquote>{e(f['text'])}</blockquote><p><small>Confidence: {e(f['conf'])}</small></p></html>"
    )


class EnrichBody(BaseModel):
    domain: str
    person_name: str | None = None
    title: str | None = None


@router.post("/tools/enrich", dependencies=[Depends(webhook_guard)])
def enrich(body: EnrichBody, db: Db = Depends(db_dep)) -> dict:
    """Enrichment record for a domain. A domain already in this workspace serves its seed facts. Otherwise this
    proxies Apollo.io when APOLLO_API_KEY is set, and returns an empty record when it isn't or Apollo has nothing."""
    row = db.q1("select p.* , c.name as company from prospects p join companies c on c.id = p.company_id where c.domain = %s order by p.id limit 1", (body.domain,))
    if row:
        facts = [{"statement": f["text"], "source_url": f["url"], "confidence": {"High": 0.9, "Medium": 0.7}.get(f["conf"], 0.5)} for f in [*row["facts"], *row["rich"]]]
        return {"company": {"name": row["company"], "domain": body.domain}, "person": {"name": row["full_name"], "title": row["title"]}, "facts": facts}
    if not get_settings().apollo_api_key:
        return {"company": None, "person": None, "facts": []}
    try:
        rec = apollo.enrich_domain(body.domain, body.person_name)
    except apollo.ApolloUnavailable:
        return {"company": None, "person": None, "facts": []}
    org, person = rec["company"], rec["person"]
    site = org.website_url or (f"https://{org.domain}" if org.domain else "")
    facts = []
    if org.description:
        facts.append({"statement": org.description, "source_url": site, "confidence": 0.7})
    if org.staff:
        facts.append({"statement": f"{org.name} has about {org.staff:,} staff.", "source_url": site, "confidence": 0.9})
    if person and person.linkedin_url:
        facts.append({"statement": f"{person.name} is listed as {person.title or 'a contact'} at {org.name} on LinkedIn.", "source_url": person.linkedin_url, "confidence": 0.9})
    return {
        "company": {"name": org.name, "domain": org.domain or body.domain} if org.name else None,
        "person": {"name": person.name, "title": person.title} if person else None,
        "facts": facts,
    }


@router.get("/tools/linkedin-finder.js")
def linkedin_finder_download() -> FileResponse:
    """The real local-runner script, downloadable from the live site. Run it on your own laptop with your
    own logged-in LinkedIn session; see MANUAL_ACTIONS.md MA-14 for the exact command."""
    if not SCRIPT_PATH.exists():
        raise NotFound("linkedin_find_employees.js is not present on this deployment")
    return FileResponse(SCRIPT_PATH, media_type="application/javascript", filename="linkedin_find_employees.js")


class LinkedInImportBody(BaseModel):
    campaign_id: str
    company: str
    domain: str = ""
    people: list[dict]


@router.post("/tools/linkedin-import", dependencies=[Depends(webhook_guard)])
def linkedin_import(body: LinkedInImportBody, db: Db = Depends(db_dep)) -> dict:
    """Receives what scripts/linkedin_find_employees.js found on someone's own laptop and creates real
    prospects from it - see backend/orchestrator/discovery.py:import_linkedin for the company-enrichment
    and email-lookup steps."""
    return discovery.import_linkedin(db, body.campaign_id, body.company, body.domain, body.people)
