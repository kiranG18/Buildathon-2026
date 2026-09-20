# API

FastAPI serves OpenAPI at `/docs` and `/redoc`. `make schemas` exports `docs/openapi.json`. Every route except `/health`, `/auth/login`, `/demo-sources/*` and the signed webhooks needs `Authorization: Bearer <jwt>`.

Errors: `{"error": {"code", "message", "request_id"}}`. Status codes: 400 validation, 401 no or bad token, 403 wrong role, 404 missing, 409 state conflict or a gate refusal, 429 rate limit, 502 upstream or database failure.

Roles: `Admin` (everything), `Manager` (campaigns, prompts, controls, kill switch), `Rep` (own campaigns, own escalations, human replies).

## Auth and state

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/auth/login` | POST | `{email, password}` returns `{token, user}` |
| `/auth/password` | POST | `{current, new}` changes the signed-in user's own password (8 characters or more) |
| `/state` | GET | The whole workspace the UI reads. Reps get only their campaigns |
| `/state/sig` | GET | A cheap signature the UI polls every 3 seconds. The UI fetches `/state` only when it changes |

## Campaigns and control

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/campaigns` | GET, POST | List with counts. Create a Draft |
| `/campaigns/{id}` | GET, PATCH | Config with checklist. Every edit writes a `campaign_versions` snapshot |
| `/campaigns/{id}/dashboard` | GET | Funnel, stats, agent counters, alerts |
| `/campaigns/{id}/dry-run` | POST | Writer plus grounding check on three sample prospects. Nothing is stored |
| `/campaigns/{id}/activate` | POST | 200, or 409 with the failing checklist items |
| `/campaigns/{id}/pause`, `/resume` | POST | Pause writes one row. Resume re-queues held jobs |
| `/campaigns/{id}/complete`, `/archive`, `/duplicate` | POST | Lifecycle and A/B variants |
| `/campaigns/{id}/agents/{agent}` | PUT | Agent-level stop |
| `/campaigns/{id}/channels/{channel}` | PUT | Channel-level stop, replans onto the remaining channels |
| `/campaigns/{id}/discover`, `/prospects/import` | POST | Demo discovery and CSV import |
| `/kill-switch` | GET, POST | Global stop. Admin and manager |

## Prompts and evals

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/campaigns/{id}/prompts` | GET, POST | Versions per role. Save a new version (lint runs first) |
| `/campaigns/{id}/prompts/diff` | GET | Diff of two versions |
| `/prompts/{version_id}/activate` | POST | Atomic: archive the active version, activate the chosen one, write an audit event. `{"rollback": true}` for a rollback |
| `/campaigns/{id}/prompts/{role}/golden` | POST | Run the golden set for a version and store the score |
| `/campaigns/{id}/prompts/{role}/coach` | POST | Draft an improved version from the failing cases. Never activates |
| `/agent-runs/{id}/replay` | POST | Re-run one run against another prompt version, tagged REPLAY |

## Prospects, activity and traces

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/prospects`, `/prospects/{id}` | GET | Explorer and detail |
| `/enrollments/{id}/run` | POST | Queue research now (the Run now button) |
| `/enrollments/{id}/stop`, `/escalate`, `/reassign`, `/reply` | POST | Manual controls and human replies |
| `/activity` | GET | Feed with a `since_id` cursor |
| `/agent-runs`, `/agent-runs/{id}` | GET | Agent Activity table and the decision trace |
| `/agent-runs/{id}/retry` | POST | Retry a failed job |
| `/outreach/send` | POST | Ask the Guardian to authorize a send. A refusal is a 409 with every check listed |
| `/demo/simulate-reply` | POST | Reply simulator through the real `ingest_reply` |

## Approvals, escalations, conflicts

`GET /approvals`, `POST /approvals/{id}/decide` (`approve` with optional `edited_body`, or `reject` with a reason), `GET /escalations`, `POST /escalations/{id}/resolve`, `POST /escalations/{id}/reassign`, `GET /conflicts`, `POST /conflicts/{id}/resolve`.

## Reps, suppression, integrations, demo tools

`GET /reps`, `POST /users` (admin only: `{name, role, email?, rep_limit?}` returns the new user and a generated password, shown once), `PATCH /reps/{id}`, `GET /reps/{id}/affected`, `POST /reps/{id}/offboard`, `POST /reps/{id}/reassign`. `POST /suppression`, `DELETE /suppression/{id}`. `POST /integrations/{key}/pause`, `/mode`, `/test`. Demo mode only: `POST /demo/advance-clock`, `/demo/play-call`, `/demo/reset`.

## Analytics and knowledge

`GET /analytics/campaigns` (prospects, contacted, reply rate, positive rate, meeting rate, cost per prospect, per qualified lead, per conversation), `GET /analytics/agents`, `GET /analytics/prompt-versions`. `POST /knowledge/search`, `POST /knowledge/documents`, `POST /knowledge/documents/{id}/reingest`, `DELETE /knowledge/documents/{id}`.

## Webhooks and tools (shared secret or signature)

| Endpoint | Header | Purpose |
| --- | --- | --- |
| `POST /inbound/{channel}` | `X-Cadence-Secret` | One inbound function for every channel |
| `POST /webhooks/twilio/sms` | `X-Twilio-Signature` | Inbound SMS |
| `GET /voice/briefing/{enrollment_id}` | `X-Cadence-Secret` | DronaHQ pre-call webhook |
| `POST /voice/outcome` | `X-Cadence-Secret` | DronaHQ post-call webhook |
| `POST /tools/enrich` | `X-Cadence-Secret` | Enrichment record for the Researcher |
| `/mcp` | `Authorization: Bearer <MCP_TOKEN>` | MCP over Streamable HTTP: `search_knowledge`, `get_timeline`, `save_research`, `propose_slots`, `book_meeting`, `create_escalation`, `set_classification` |

## Examples

```bash
BASE=http://localhost:8000
TOKEN=$(curl -s $BASE/auth/login -H 'Content-Type: application/json' -d '{"email":"ava@helix.demo","password":"helix-demo"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
H="Authorization: Bearer $TOKEN"

curl -s -X POST $BASE/campaigns/C2/pause -H "$H"                       # pause one campaign
curl -s -X POST $BASE/kill-switch -H "$H" -H 'Content-Type: application/json' -d '{"active":true}'
curl -s -X POST $BASE/demo/simulate-reply -H "$H" -H 'Content-Type: application/json' \
  -d '{"enrollment_id":"E1","channel":"email","body":"Interested, tell me more."}'
curl -s -X POST $BASE/outreach/send -H "$H" -H 'Content-Type: application/json' \
  -d '{"enrollment_id":"E93","channel":"email"}'                       # a Draft campaign refuses: campaign_not_live
```
