import logging

import pytest

from backend.core.config import get_settings

pytestmark = pytest.mark.readonly


def test_au1_every_route_needs_a_token_except_health_login_and_signed_webhooks(seeded, client):
    for method, path in [("get", "/state"), ("get", "/campaigns"), ("get", "/prospects"), ("get", "/approvals"), ("get", "/reps"), ("get", "/kill-switch"),
                         ("get", "/analytics/campaigns"), ("post", "/campaigns/C1/pause"), ("post", "/knowledge/search")]:
        assert getattr(client, method)(path).status_code == 401, path
    assert client.get("/health").status_code == 200


def test_au4_expired_or_tampered_tokens_are_rejected(seeded, client, auth):
    import jwt

    good = auth()["Authorization"].split(" ", 1)[1]
    forged = jwt.encode({"sub": "U1", "role": "Admin"}, "not-the-secret", algorithm="HS256")
    assert client.get("/state", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    assert client.get("/state", headers={"Authorization": f"Bearer {good[:-3]}abc"}).status_code == 401
    expired = jwt.encode({"sub": "U2", "role": "Manager", "exp": 1}, get_settings().jwt_secret, algorithm="HS256")
    assert client.get("/state", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_se1_webhooks_need_the_shared_secret(seeded, client, auth):
    body = {"enrollment_id": "E1", "body": "hello"}
    assert client.post("/inbound/email", json=body).status_code == 401
    assert client.post("/inbound/email", json=body, headers={"X-Cadence-Secret": "wrong"}).status_code == 401
    ok = client.post("/inbound/email", json=body, headers={"X-Cadence-Secret": get_settings().webhook_shared_secret})
    assert ok.status_code in (200, 404)


def test_se5_sql_injection_in_a_search_parameter_is_inert(seeded, client, auth):
    r = client.get("/prospects", headers=auth(), params={"q": "'; drop table prospects;--"})
    assert r.status_code == 200 and r.json()["items"] == []
    assert client.get("/prospects", headers=auth()).json()["items"]
    r2 = client.post("/knowledge/search", headers=auth(), json={"campaign_id": "C1", "query": "x'); drop table knowledge_chunks;--"})
    assert r2.status_code == 200


def test_se6_cors_allows_only_the_configured_origin(seeded, client):
    ok = client.options("/state", headers={"Origin": "http://localhost:8000", "Access-Control-Request-Method": "GET"})
    bad = client.options("/state", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:8000"
    assert "access-control-allow-origin" not in bad.headers


def test_se7_logs_carry_ids_but_no_email_addresses_or_message_bodies(seeded, client, auth, caplog):
    with caplog.at_level(logging.INFO):
        client.post("/auth/login", json={"email": "ava@helix.demo", "password": "helix-demo"})
        client.get("/state", headers=auth())
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "@helix.demo" not in text and "helix-demo" not in text


def test_se8_ten_wrong_logins_a_minute_hit_the_rate_limit(seeded, client):
    codes = [client.post("/auth/login", json={"email": "ava@helix.demo", "password": "nope"}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and 429 in codes[10:]


def test_au5_a_wrong_password_and_an_unknown_email_look_identical(seeded, client):
    a = client.post("/auth/login", json={"email": "ava@helix.demo", "password": "x"}).json()
    b = client.post("/auth/login", json={"email": "nobody@helix.demo", "password": "x"}).json()
    assert a["error"]["code"] == b["error"]["code"] and a["error"]["message"] == b["error"]["message"]


def test_production_refuses_to_start_with_dev_secrets():
    from pydantic import ValidationError

    from backend.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(app_env="production")
