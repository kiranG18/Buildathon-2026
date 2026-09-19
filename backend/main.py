import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg import OperationalError
from psycopg import errors as pgerr

from backend.api import (
    analytics,
    approvals,
    auth,
    campaigns,
    channels,
    controls,
    knowledge,
    prompts,
    prospects,
    public,
    sources,
    state,
    voice,
    workflow,
)
from backend.channels.adapters import register_configured
from backend.core import logging as clog
from backend.core.config import get_settings
from backend.core.db import close_pool, pool, tx
from backend.core.errors import CadenceError, GateBlocked
from backend.mcp.server import McpGate

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
ROUTERS = (auth, state, campaigns, prompts, prospects, workflow, approvals, controls, channels, voice, analytics, knowledge, public, sources)
mcp_gate = McpGate()


def envelope(code: str, message: str, status: int, extra: dict | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "request_id": clog.request_id_var.get()}}
    if extra:
        body["error"].update(extra)
    return JSONResponse(body, status_code=status)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    clog.setup(settings.log_level)
    pool()
    register_configured()
    await mcp_gate.start()
    worker = None
    if settings.embedded_worker:
        from backend.orchestrator.worker import start_embedded

        worker = start_embedded()
    yield
    if worker:
        worker.stop()
    await mcp_gate.stop()
    close_pool()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Cadence API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        clog.request_id_var.set(rid)
        t = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            clog.log().exception("unhandled error", extra={"path": request.url.path, "method": request.method})
            return envelope("internal_error", "Something went wrong on our side", 500)
        response.headers["x-request-id"] = rid
        if request.url.path not in ("/health", "/state/sig"):
            clog.log().info(
                "request", extra={"path": request.url.path, "method": request.method, "status": response.status_code, "duration_ms": int((time.monotonic() - t) * 1000)}
            )
        return response

    @app.exception_handler(GateBlocked)
    async def gate_handler(request: Request, exc: GateBlocked):
        return envelope(exc.code, exc.message, exc.status, {"decision": exc.decision, **exc.detail})

    @app.exception_handler(CadenceError)
    async def cadence_handler(request: Request, exc: CadenceError):
        return envelope(exc.code, exc.message, exc.status, exc.extra)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        return envelope("validation_error", f"{loc}: {first.get('msg', 'invalid request')}".strip(": "), 400)

    @app.exception_handler(pgerr.QueryCanceled)
    async def timeout_handler(request: Request, exc):
        return envelope("db_timeout", "The database took too long. Retry in a moment", 502)

    @app.exception_handler(OperationalError)
    async def db_handler(request: Request, exc):
        return envelope("db_unavailable", "The database is unavailable. Retry in a moment", 502)

    @app.get("/health")
    def health() -> dict:
        with tx() as db:
            db.q1("select 1 as ok")
        return {"status": "ok", "env": get_settings().app_env}

    for module in ROUTERS:
        app.include_router(module.router)
    for path in ("/mcp", "/mcp/"):
        app.add_route(path, mcp_gate, methods=["GET", "POST", "DELETE"])
    if FRONTEND.exists():
        app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
    return app


app = create_app()
