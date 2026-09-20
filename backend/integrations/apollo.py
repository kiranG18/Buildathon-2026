"""Apollo.io client: real people and companies matching a campaign's ICP.

One HTTP call per discovery batch (`search_people`), one reveal call per hit
(`reveal_contact`, since search results mask personal emails), and one lookup
for the enrichment tool (`enrich_domain`). Same shape as `agents/llm_client.py`:
an injectable transport for tests, a typed unavailable exception, short
timeouts and one retry on 429/5xx. Callers (discovery.py, sources.py) decide
what to do when this raises — today that is always "fall back to the seeded
pool," never a crash.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from backend.core.config import get_settings
from backend.core.logging import log

BASE = "https://api.apollo.io/api/v1"
TIMEOUT_S = 15
RETRIES = 1


class ApolloUnavailable(Exception):
    """No key, timeout, 429 or non-2xx. Callers must fall back, never crash the request."""


@dataclass
class ApolloOrg:
    name: str
    domain: str
    website_url: str
    industry: str = ""
    staff: int = 0
    city: str = ""
    description: str = ""
    keywords: list[str] = field(default_factory=list)


@dataclass
class ApolloPerson:
    apollo_id: str
    name: str
    title: str
    email: str
    email_locked: bool
    linkedin_url: str
    phone: str
    org: ApolloOrg


Transport = Callable[[str, str, dict], dict]
_transport: Transport | None = None


def set_transport(fn: Transport | None) -> None:
    global _transport
    _transport = fn


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S)


def _call(method: str, path: str, params_or_body: dict) -> dict:
    key = get_settings().apollo_api_key
    if not key:
        raise ApolloUnavailable("APOLLO_API_KEY is not set")
    if _transport is not None:
        return _transport(method, path, params_or_body)
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            with _client() as c:
                headers = {"x-api-key": key, "Content-Type": "application/json"}
                r = c.get(f"{BASE}{path}", headers=headers, params=params_or_body) if method == "GET" else c.post(f"{BASE}{path}", headers=headers, json=params_or_body)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            last = e
            if e.response.status_code not in (429, 500, 502, 503, 504) or attempt == RETRIES:
                break
        except httpx.HTTPError as e:
            last = e
            if attempt == RETRIES:
                break
    log().warning("apollo call failed", extra={"event": "apollo_fallback", "status": type(last).__name__ if last else "unknown"})
    raise ApolloUnavailable(f"apollo request failed: {type(last).__name__ if last else 'unknown'}") from last


def _post(path: str, body: dict) -> dict:
    return _call("POST", path, body)


def _org(raw: dict | None) -> ApolloOrg:
    raw = raw or {}
    return ApolloOrg(
        name=raw.get("name") or "",
        domain=raw.get("primary_domain") or raw.get("domain") or "",
        website_url=raw.get("website_url") or "",
        industry=raw.get("industry") or "",
        staff=int(raw.get("estimated_num_employees") or 0),
        city=", ".join(x for x in (raw.get("city"), raw.get("state") or raw.get("country")) if x),
        description=raw.get("short_description") or "",
        keywords=list(raw.get("keywords") or [])[:8],
    )


def _person(raw: dict) -> ApolloPerson:
    email = raw.get("email") or ""
    locked = not email or "not_unlocked" in email or "email_unavailable" in email
    return ApolloPerson(
        apollo_id=raw.get("id") or "",
        name=raw.get("name") or f"{raw.get('first_name', '')} {raw.get('last_name', '')}".strip(),
        title=raw.get("title") or "",
        email="" if locked else email,
        email_locked=locked,
        linkedin_url=raw.get("linkedin_url") or "",
        phone=(raw.get("phone_numbers") or [{}])[0].get("sanitized_number", "") if raw.get("phone_numbers") else "",
        org=_org(raw.get("organization")),
    )


def search_people(titles: list[str], locations: list[str], keywords: list[str], k: int) -> list[ApolloPerson]:
    """One page of real people matching the ICP. Raises ApolloUnavailable on any transport failure."""
    body = {"page": 1, "per_page": max(1, min(k, 25))}
    if titles:
        body["person_titles"] = titles
    if locations:
        body["person_locations"] = locations
    if keywords:
        body["q_organization_keyword_tags"] = keywords[:10]
    data = _post("/mixed_people/search", body)
    return [_person(p) for p in data.get("people", [])]


def reveal_contact(apollo_id: str) -> ApolloPerson | None:
    """Real email/phone for one person, since search results mask personal emails."""
    data = _post("/people/match", {"id": apollo_id, "reveal_personal_emails": True})
    p = data.get("person")
    return _person(p) if p else None


def enrich_domain(domain: str, person_name: str | None = None) -> dict:
    """Real company facts for a domain (organizations/enrich - available on every Apollo plan, including free).

    Person match (people/match) needs a paid Apollo plan. It's attempted only when a name is given, and its
    failure never blocks the company data: a 403 there still returns real company facts, just no person."""
    person = None
    if person_name:
        parts = person_name.split(" ", 1)
        body = {"first_name": parts[0], "last_name": parts[1] if len(parts) > 1 else "", "domain": domain, "reveal_personal_emails": True}
        try:
            raw = _post("/people/match", body).get("person")
            if raw:
                person = _person(raw)
        except ApolloUnavailable:
            person = None
    org_data = _call("GET", "/organizations/enrich", {"domain": domain})
    return {"company": _org(org_data.get("organization")), "person": person}
