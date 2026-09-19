import os

import psycopg
import pytest

BASE = os.environ.get("DATABASE_URL", "postgresql://cadence:cadence@localhost:5433/cadence")
TEST_DB = "cadence_test"
admin_url = BASE.rsplit("/", 1)[0] + "/postgres"
os.environ["DATABASE_URL"] = BASE.rsplit("/", 1)[0] + f"/{TEST_DB}"
os.environ["LLM_MODE"] = "fake"
os.environ["FAKE_LATENCY_MS"] = "0"

with psycopg.connect(admin_url, autocommit=True) as c:
    if not c.execute("select 1 from pg_database where datname = %s", (TEST_DB,)).fetchone():
        c.execute(f"create database {TEST_DB}")

from backend.core import clock  # noqa: E402
from backend.core.db import close_pool, migrate  # noqa: E402
from backend.core.security import login_failures  # noqa: E402
from scripts.load_seed import load  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    migrate(reset=True)
    yield
    close_pool()


_state = {"dirty": True}


def pytest_configure(config):
    config.addinivalue_line("markers", "readonly: the test does not change data, so the seeded workspace is reused")


@pytest.fixture
def seeded(request):
    """Rebuild the seeded demo workspace unless the previous test left it untouched."""
    clock.set_frozen(None)
    clock.invalidate()
    if _state["dirty"]:
        load()
    _state["dirty"] = "readonly" not in request.keywords
    login_failures.reset()
    yield
    clock.set_frozen(None)


@pytest.fixture
def client(seeded):
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth(client):
    def login(email: str = "ava@helix.demo") -> dict:
        r = client.post("/auth/login", json={"email": email, "password": "helix-demo"})
        assert r.status_code == 200, r.text
        return {"Authorization": "Bearer " + r.json()["token"]}

    return login
