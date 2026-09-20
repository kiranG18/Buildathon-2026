"""Apollo-backed discovery: real people when a key is set, the seeded pool when it isn't or Apollo fails."""

import pytest

from backend.core.config import get_settings
from backend.integrations import apollo
from backend.orchestrator import discovery
from backend.orchestrator.repo import campaign
from tests.helpers import scratch

pytestmark = pytest.mark.readonly

PERSON = {
    "id": "apollo-1",
    "first_name": "Priya",
    "last_name": "Nathan",
    "name": "Priya Nathan",
    "title": "VP Engineering",
    "email": "priya.nathan@realcorp.example",
    "linkedin_url": "https://www.linkedin.com/in/priya-nathan-real",
    "phone_numbers": [{"sanitized_number": "+1 415 555 0199"}],
    "organization": {
        "name": "Realcorp",
        "primary_domain": "realcorp.example",
        "website_url": "https://realcorp.example",
        "industry": "B2B SaaS",
        "estimated_num_employees": 420,
        "short_description": "Builds internal tooling for mid-market operations teams.",
        "city": "Austin",
        "state": "TX",
    },
}
LOCKED_PERSON = {**PERSON, "id": "apollo-2", "name": "Jordan Reyes", "email": "email_not_unlocked@realcorp.example"}


@pytest.fixture(autouse=True)
def _clear_transport():
    yield
    apollo.set_transport(None)


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "apollo_api_key", "test-key")
    yield
    monkeypatch.setattr(get_settings(), "apollo_api_key", "")


def test_search_people_maps_icp_filters_and_parses_a_real_hit(with_key):
    calls = []

    def transport(method, path, body):
        calls.append((method, path, body))
        return {"people": [PERSON]}

    apollo.set_transport(transport)
    out = apollo.search_people(["VP Engineering"], ["Austin"], ["saas"], 3)

    assert calls[0][:2] == ("POST", "/mixed_people/search")
    assert calls[0][2]["person_titles"] == ["VP Engineering"]
    assert calls[0][2]["person_locations"] == ["Austin"]
    assert calls[0][2]["per_page"] == 3
    assert len(out) == 1 and out[0].name == "Priya Nathan" and out[0].email == "priya.nathan@realcorp.example"
    assert out[0].org.domain == "realcorp.example" and out[0].org.staff == 420


def test_reveal_contact_unlocks_a_masked_email(with_key):
    apollo.set_transport(lambda method, path, body: {"person": PERSON} if path == "/people/match" else {})
    revealed = apollo.reveal_contact("apollo-1")
    assert revealed.email == "priya.nathan@realcorp.example"


def test_no_key_raises_unavailable():
    with pytest.raises(apollo.ApolloUnavailable):
        apollo.search_people([], [], [], 1)


def test_discover_creates_a_real_prospect_with_a_real_source_url(with_key, seeded):
    apollo.set_transport(lambda method, path, body: {"people": [PERSON]})
    with scratch() as db:
        c = campaign(db, "C1")
        made = discovery._discover_live(db, c, "C1", "C1", 1)
        assert len(made) == 1
        row = db.q1("select * from prospects where id = 'priya-nathan'")
        assert row["email"] == "priya.nathan@realcorp.example"
        assert row["linkedin_url"] == "https://www.linkedin.com/in/priya-nathan-real"
        assert row["facts"][0]["url"] == "https://realcorp.example"
        assert not row["facts"][0]["url"].startswith("/demo-sources/")


def test_discover_reveals_a_locked_email_before_creating_the_prospect(with_key, seeded):
    def transport(method, path, body):
        if path == "/mixed_people/search":
            return {"people": [LOCKED_PERSON]}
        assert path == "/people/match" and body["id"] == "apollo-2"
        return {"person": PERSON}

    apollo.set_transport(transport)
    with scratch() as db:
        c = campaign(db, "C1")
        made = discovery._discover_live(db, c, "C1", "C1", 1)
        assert len(made) == 1
        assert db.q1("select email from prospects where id = 'priya-nathan'")["email"] == "priya.nathan@realcorp.example"


def test_discover_falls_back_to_the_seeded_pool_when_apollo_is_unavailable(seeded):
    """No key set at all: discover() must behave exactly as before, no crash."""
    with scratch() as db:
        before = db.q1("select count(*) as n from prospects")["n"]
        made = discovery.discover(db, "C1", 1)
        assert len(made) == 1
        assert db.q1("select count(*) as n from prospects")["n"] == before + 1


def test_discover_falls_back_when_apollo_errors(with_key, seeded):
    def transport(method, path, body):
        raise apollo.ApolloUnavailable("boom")

    apollo.set_transport(transport)
    with scratch() as db:
        made = discovery.discover(db, "C1", 1)
        assert len(made) == 1
        row = db.q1("select p.* from prospects p join enrollments e on e.prospect_id = p.id where e.id = %s", (made[0]["id"],))
        assert row["email"].endswith("@gmail.com")
