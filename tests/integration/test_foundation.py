import pytest

from backend.core.db import tx

pytestmark = pytest.mark.readonly


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_login_roles_and_bad_password(client):
    for email, role in [("admin@helix.demo", "Admin"), ("ava@helix.demo", "Manager"), ("marcus@helix.demo", "Rep")]:
        r = client.post("/auth/login", json={"email": email, "password": "helix-demo"})
        assert r.status_code == 200 and r.json()["user"]["role"] == role
    bad = client.post("/auth/login", json={"email": "ava@helix.demo", "password": "nope"})
    unknown = client.post("/auth/login", json={"email": "ghost@helix.demo", "password": "nope"})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_no_token_is_401_and_tampered_token_is_401(client, auth):
    assert client.get("/state").status_code == 401
    h = auth()
    assert client.get("/state", headers={"Authorization": h["Authorization"] + "x"}).status_code == 401


def test_seed_counts(client, auth):
    s = client.get("/state", headers=auth()).json()
    statuses = sorted(c["status"] for c in s["camps"])
    assert statuses == ["draft", "live", "live", "live"]
    assert len([e for e in s["enr"] if e["cid"] != "C4"]) == 90
    assert len([a for a in s["approvals"] if a["status"] == "open"]) == 10
    assert len(s["people"]) == 93


def test_rep_sees_only_own_campaigns(client, auth):
    s = client.get("/state", headers=auth("priya@helix.demo")).json()
    assert {c["id"] for c in s["camps"]} == {"C2", "C4"}
    assert all(e["cid"] in ("C2", "C4") for e in s["enr"])
    assert all(x["rep"] == "U4" for x in s["escal"])
    assert s["conflicts"] == [] and s["suppress"] == []


def test_error_envelope(client, auth):
    r = client.get("/state", headers={"Authorization": "Bearer nope"})
    assert set(r.json()["error"]) == {"code", "message", "request_id"}


def test_migrations_create_required_indexes():
    with tx() as db:
        idx = {r["indexname"] for r in db.q("select indexname from pg_indexes where schemaname = 'public'")}
    for name in ("prompt_one_active", "claims_one_active", "knowledge_chunks_hnsw", "knowledge_chunks_tsv"):
        assert name in idx


def test_state_is_served_from_memory_until_something_changes(seeded, client, auth, monkeypatch):
    from backend.api import state as state_api
    from backend.core.db import tx

    calls = []
    real = state_api.build_state
    monkeypatch.setattr(state_api, "build_state", lambda db, user: calls.append(1) or real(db, user))
    state_api._cache.clear()
    first = client.get("/state", headers=auth()).json()
    second = client.get("/state", headers=auth()).json()
    assert len(calls) == 1 and second["camps"] == first["camps"] and second["now"] >= first["now"]
    with tx() as db:
        db.x("update campaigns set version = version + 1 where id = 'C4'")
    try:
        client.get("/state", headers=auth())
        assert len(calls) == 2
    finally:
        with tx() as db:
            db.x("update campaigns set version = version - 1 where id = 'C4'")
        state_api._cache.clear()


def test_state_reflects_a_rep_reassignment_immediately(seeded, client, auth):
    mgr = auth("ava@helix.demo")
    before = client.get("/state", headers=mgr).json()
    e = next(x for x in before["enr"] if x["rep"] and x["rep"] != "U3")
    assert client.post(f"/enrollments/{e['id']}/reassign", headers=mgr, json={"replacement_rep_id": "U3"}).status_code == 200
    after = client.get("/state", headers=mgr).json()
    assert next(x for x in after["enr"] if x["id"] == e["id"])["rep"] == "U3"


def test_reassigning_a_prospect_grants_the_new_rep_visibility_on_their_own_dashboard(seeded, client, auth):
    """A rep's /state only shows enrollments in campaigns they're assigned to. Reassigning one enrollment to a rep
    who isn't on that campaign must grant that campaign, or the rep can never see the prospect they were just given."""
    mgr, rep = auth("ava@helix.demo"), auth("marcus@helix.demo")
    before = client.get("/state", headers=mgr).json()
    e = next(x for x in before["enr"] if x["cid"] not in {c["id"] for c in client.get("/state", headers=rep).json()["camps"]})
    assert e["id"] not in {x["id"] for x in client.get("/state", headers=rep).json()["enr"]}
    assert client.post(f"/enrollments/{e['id']}/reassign", headers=mgr, json={"replacement_rep_id": "U3"}).status_code == 200
    after_rep = client.get("/state", headers=rep).json()
    assert e["id"] in {x["id"] for x in after_rep["enr"]}
    assert e["cid"] in {c["id"] for c in after_rep["camps"]}
