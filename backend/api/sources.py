"""Hosted source pages for the demo prospects, and the enrichment tool the DronaHQ Researcher calls.

Fictional companies have no web presence, so every fact keeps a real URL on this API. A judge who clicks an evidence link lands on the page the fact came from.
"""

import html

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from backend.core.db import Db
from backend.core.errors import NotFound
from backend.core.security import db_dep, webhook_guard

router = APIRouter()

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
    """Enrichment record for a domain. Demo mode serves the seed facts. With an Apollo key this would proxy Apollo."""
    row = db.q1("select p.* , c.name as company from prospects p join companies c on c.id = p.company_id where c.domain = %s order by p.id limit 1", (body.domain,))
    if not row:
        return {"company": None, "person": None, "facts": []}
    facts = [{"statement": f["text"], "source_url": f["url"], "confidence": {"High": 0.9, "Medium": 0.7}.get(f["conf"], 0.5)} for f in [*row["facts"], *row["rich"]]]
    return {"company": {"name": row["company"], "domain": body.domain}, "person": {"name": row["full_name"], "title": row["title"]}, "facts": facts}
