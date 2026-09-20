"""discovery.import_linkedin: real people from scripts/linkedin_find_employees.js become real prospects,
with a real Hunter-verified email when available and a clearly-labelled sandbox placeholder otherwise."""

import pytest

from backend.core.config import get_settings
from backend.integrations import apollo, hunter
from backend.orchestrator import discovery
from tests.helpers import scratch

pytestmark = pytest.mark.readonly

PEOPLE = [
    {"name": "Dana Okoye", "title": "Head of Platform", "profile_url": "https://www.linkedin.com/in/dana-okoye-real"},
    {"name": "", "title": "CTO", "profile_url": "https://www.linkedin.com/in/nobody"},  # dropped: no name
]
ORG = {
    "name": "Realcorp",
    "primary_domain": "realcorp.example",
    "website_url": "https://realcorp.example",
    "industry": "B2B SaaS",
    "estimated_num_employees": 300,
    "short_description": "Builds internal tooling.",
    "city": "Austin",
}


@pytest.fixture(autouse=True)
def _clear_transports():
    yield
    apollo.set_transport(None)
    hunter.set_transport(None)


@pytest.fixture
def with_keys(monkeypatch):
    monkeypatch.setattr(get_settings(), "apollo_api_key", "a-key")
    monkeypatch.setattr(get_settings(), "hunter_api_key", "h-key")
    yield
    monkeypatch.setattr(get_settings(), "apollo_api_key", "")
    monkeypatch.setattr(get_settings(), "hunter_api_key", "")


def test_creates_a_real_prospect_with_a_hunter_verified_email(with_keys, seeded):
    apollo.set_transport(lambda method, path, body: {"organization": ORG} if path == "/organizations/enrich" else {})
    hunter.set_transport(lambda params: {"data": {"email": "dana.okoye@realcorp.example", "score": 92, "verification": {"status": "valid"}}})

    with scratch() as db:
        out = discovery.import_linkedin(db, "C1", "Realcorp", "realcorp.example", PEOPLE)
        assert out["created"] == 1 and out["skipped"] == 1  # the nameless entry is dropped

        row = db.q1("select * from prospects where id = 'dana-okoye'")
        assert row["full_name"] == "Dana Okoye"
        assert row["email"] == "dana.okoye@realcorp.example"
        assert row["linkedin_url"] == "https://www.linkedin.com/in/dana-okoye-real"
        assert row["facts"][0]["url"] == "https://www.linkedin.com/in/dana-okoye-real"
        assert row["rich"] == []  # verified email: no "unverified" flag fact


def test_falls_back_to_a_sandbox_email_when_hunter_has_nothing(with_keys, seeded):
    apollo.set_transport(lambda method, path, body: {"organization": ORG} if path == "/organizations/enrich" else {})
    hunter.set_transport(lambda params: {"data": {}})  # a clean miss

    with scratch() as db:
        discovery.import_linkedin(db, "C1", "Realcorp", "realcorp.example", PEOPLE[:1])
        row = db.q1("select * from prospects where id = 'dana-okoye'")
        assert row["email"].endswith("@gmail.com")
        assert row["rich"] and "not verified" in row["rich"][0]["text"]


def test_works_with_no_domain_and_no_keys_at_all(seeded):
    """The bare minimum: LinkedIn gave a name, title and profile URL. Nothing else is required."""
    with scratch() as db:
        out = discovery.import_linkedin(db, "C1", "Some Startup", "", [{"name": "Jamie Fox", "title": "Founder", "profile_url": "https://www.linkedin.com/in/jamie-fox-x"}])
        assert out["created"] == 1
        row = db.q1("select * from prospects where id = 'jamie-fox'")
        assert row["email"].endswith("@gmail.com") and row["linkedin_url"] == "https://www.linkedin.com/in/jamie-fox-x"


def test_dedupes_on_linkedin_url(with_keys, seeded):
    apollo.set_transport(lambda method, path, body: {"organization": ORG})
    hunter.set_transport(lambda params: {"data": {}})
    with scratch() as db:
        discovery.import_linkedin(db, "C1", "Realcorp", "realcorp.example", PEOPLE[:1])
        out = discovery.import_linkedin(db, "C1", "Realcorp", "realcorp.example", PEOPLE[:1])
        assert out["created"] == 0 and out["skipped"] == 1
