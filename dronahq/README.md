# DronaHQ in Cadence

Cadence is built on DronaHQ in three places, and each one is a production path that stops working without it.

| Component | What it does | What breaks without it |
| --- | --- | --- |
| Apps Studio app `Cadence` | Hosts the manager control plane. The static UI in `frontend/` is embedded in a web component, and native screens read the same REST API | The judge-facing URL and the manager's workspace |
| Agentic platform: Researcher | Web search and enrichment per prospect, saves sourced facts through our MCP tool `save_research` | Research on DronaHQ. The direct provider takes over (`AGENT_PROVIDER_RESEARCHER=direct`) |
| Agentic platform: Responder | Reads inbound replies with MCP tools, classifies, drafts, books or escalates | Reply handling on DronaHQ. The direct provider takes over |
| Voice Agent: Caller | Places one real call with a briefing fetched from our API, posts the outcome back | Live calls. The scripted outcome path runs in sandbox |

Our own code holds the state machine, the policy gate, the conflict engine, RAG, channels, the MCP server and every rule that decides whether an action may happen. No DronaHQ agent can send anything: every send passes the Guardian.

## Files

- `agents/researcher.md`, `agents/responder.md`, `agents/caller.md`: instruction shells to paste into the platform.
- `../agents/schemas/researcher.json`, `responder.json`: Structured Output schemas, exported from the Pydantic models by `make schemas`.
- `app-spec.md`: every native Apps Studio screen with its endpoint bindings.
- `vibe-prompts.md`: the Vibe Coding prompts used for each screen archetype.
- `screenshots/`: agent instructions, tool lists and run traces, saved after setup.

## Setup order

The exact click path is `../MANUAL_ACTIONS.md`, items MA-11a to MA-11f. Every setup step ends with a verification that Claude Code runs:

1. Webhook trigger answers a payload with structured output (or answers asynchronously, and the MCP callback path takes over).
2. An MCP tool call from the agent creates a row (`save_research` writes facts and an `activity` event).
3. Both voice webhooks fire on one test call.

## How Cadence talks to DronaHQ

| Direction | Mechanism |
| --- | --- |
| App to backend | REST connector, `Authorization: Bearer <jwt>` from an app variable |
| Backend to agent | POST to the agent's Webhook trigger with the prompt bundle, memory JSON and output schema (`backend/orchestrator/dronahq.py`) |
| Agent to backend | MCP over Streamable HTTP at `/mcp` with `MCP_TOKEN`, seven tools (`backend/mcp/`) |
| Voice, before a call | `GET /voice/briefing/{enrollment_id}` |
| Voice, after a call | `POST /voice/outcome` |

Every callback carries `X-Cadence-Secret`, compared in constant time. If a hosted agent is unreachable or silent for 90 seconds, the step reruns on the direct provider and the activity feed records `provider_fallback`.
