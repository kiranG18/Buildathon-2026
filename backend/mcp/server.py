"""MCP server for DronaHQ agents: exactly seven tools over Streamable HTTP at /mcp, guarded by MCP_TOKEN."""

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from agents.models import ResponderResult
from backend.core.config import get_settings
from backend.core.security import secret_ok
from backend.mcp import tools

TOOL_NAMES = ("search_knowledge", "get_timeline", "save_research", "propose_slots", "book_meeting", "create_escalation", "set_classification")
Classification = ResponderResult.model_fields["classification"].annotation
NextAction = ResponderResult.model_fields["next_action"].annotation
Sentiment = ResponderResult.model_fields["sentiment"].annotation


def build_server() -> FastMCP:
    # The bearer token guards this endpoint and the app sits behind a proxy with its own host name, so the SDK's Host-header allow-list is switched off.
    mcp = FastMCP("Cadence", stateless_http=True, json_response=True, streamable_http_path="/",
                  transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))

    @mcp.tool()
    async def search_knowledge(campaign_id: str, query: str, doc_types: list[str] | None = None, k: int = 4) -> list[dict]:
        """Search one campaign's knowledge plus global knowledge. Returns chunks with ids you must cite."""
        return await anyio.to_thread.run_sync(lambda: tools.search_knowledge(campaign_id, query, doc_types, k))

    @mcp.tool()
    async def get_timeline(enrollment_id: str, limit: int = 20) -> dict:
        """Facts, messages across every channel, the channel plan and a summary for one enrollment."""
        return await anyio.to_thread.run_sync(lambda: tools.get_timeline(enrollment_id, limit))

    @mcp.tool()
    async def save_research(enrollment_id: str, result: dict) -> dict:
        """Save a ResearchResult: facts[] with statement, source_url and confidence. Facts under 0.5 or without a source are dropped."""
        return await anyio.to_thread.run_sync(lambda: tools.save_research(enrollment_id, result))

    @mcp.tool()
    async def propose_slots(enrollment_id: str, days: int = 5) -> list[dict]:
        """Two open meeting slots for the rep assigned to this enrollment."""
        return await anyio.to_thread.run_sync(lambda: tools.propose_slots(enrollment_id, days))

    @mcp.tool()
    async def book_meeting(enrollment_id: str, slot_start: int) -> dict:
        """Book one of the slots returned by propose_slots (slot_start is the epoch millisecond value)."""
        return await anyio.to_thread.run_sync(lambda: tools.book_meeting(enrollment_id, slot_start))

    @mcp.tool()
    async def create_escalation(enrollment_id: str, reason_code: str, summary: str, suggested_reply: str = "") -> dict:
        """Hand the thread to the human rep with a summary and a suggested reply."""
        return await anyio.to_thread.run_sync(lambda: tools.create_escalation(enrollment_id, reason_code, summary, suggested_reply))

    @mcp.tool()
    async def set_classification(
        enrollment_id: str, classification: Classification, next_action: NextAction, confidence: float = 0.8, sentiment: Sentiment = "neutral",
        objection_type: str = "", reply_draft: str = "", claims: list[str] | None = None, slots_offered: list[str] | None = None, escalation_reason: str = "", summary_update: str = "",
    ) -> dict:
        """Submit your whole decision for one inbound reply, once, after any other tool calls. claims are strings written as source_id::statement."""
        return await anyio.to_thread.run_sync(lambda: tools.set_classification(
            enrollment_id, classification, next_action, confidence, sentiment, objection_type, reply_draft, claims, slots_offered, escalation_reason, summary_update))

    return mcp


class McpGate:
    """ASGI wrapper mounted at /mcp: bearer-token check, then the request goes to the MCP app at its root path.

    The MCP session manager runs once per start(), so the app builds a fresh server each time it starts (tests start it repeatedly)."""

    def __init__(self):
        self.inner = None
        self._cm = None

    async def start(self) -> None:
        server = build_server()
        self.inner = server.streamable_http_app()
        self._cm = server.session_manager.run()
        await self._cm.__aenter__()

    async def stop(self) -> None:
        if self._cm is not None:
            await self._cm.__aexit__(None, None, None)
        self.inner = self._cm = None

    async def __call__(self, scope, receive, send):
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        token = headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not secret_ok(token, get_settings().mcp_token):
            body = b'{"error": {"code": "unauthorized", "message": "Missing or wrong MCP token"}}'
            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.inner({**scope, "path": "/", "raw_path": b"/"}, receive, send)
