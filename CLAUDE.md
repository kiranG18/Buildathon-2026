# Cadence build rules

Cadence is an autonomous multi-channel SDR with a manager control plane. The goal is a live, working product that meets every mandatory requirement (M1 to M19) in section 1 of `docs/execution-plan.md`.

## Sources of truth

Rank them in this order. The higher source wins every conflict.

1. `docs/problem-statement.pdf`: functionality and judging requirements.
2. `docs/execution-plan.md`: architecture, data model, agents, API contracts, tests, timeline.
3. `frontend/prototype/cadence-prototype.html`: the UI reference and the behavior spec. Its design language (BizLink B2B SaaS: Onest type, cream page bands, white cards, 16px radii, ink-black primary buttons) sets the look of every screen. Its logic defines the policy gate, conflict ladder, grounding check, channel planner, and the states of every screen. Port the logic to the backend. Never ship its in-browser engine.
4. `docs/design-system.md` and `frontend/css/tokens.css`: tokens and component rules already extracted from the prototype. Use them as the working style guide.

## Deadline

Sunday 20 September 2026, 11:59 PM IST. Feature freeze Sunday 6 PM. Deploy freeze 9 PM. Submit by 11 PM.

## Working loop

Plan, Build, Run, Test, Fix, UI review against the prototype, update `BUILD_STATUS.md`, commit. Repeat for every feature.

- Run the code before you say it works. Paste real test output. Report failures as failures.
- Finish one vertical slice (schema, API, worker, UI, test) before you start the next.
- Priorities follow plan section 13: P0, then P1, then P2. Shrink a mandatory requirement when time runs out. Never delete one.

## Manual stop protocol

Some steps need the human: API keys, OAuth consent, DronaHQ setup, Twilio, hosting, DNS, account settings. Follow this sequence.

1. Finish the independent tasks already listed for the current phase in `BUILD_STATUS.md`.
2. Write or update the matching `MA-xx` entry in `MANUAL_ACTIONS.md` with exact screens, exact values, and the env var names to fill.
3. Print this block and end your turn:

```
STOP: MANUAL ACTION MA-xx
Blocked work: <what cannot continue>
Do this: <numbered steps with exact values>
Reply "done MA-xx" and paste: <the values or screenshots you need back>
```

4. Wait. Continue only after the user replies. Run a smoke test against the real service, then record the result in `docs/spikes.md`.

Never invent how DronaHQ, Gmail, Twilio, or Supabase behave. Write a small spike script, run it, and record the result. Never put a real key in any file that git tracks.

## Architecture (short form, details in the plan)

- Backend: Python 3.12, FastAPI, Pydantic v2. One image, two commands: web and worker.
- Database: Postgres with pgvector and full-text search. Dev runs on Docker (`pgvector/pgvector:pg16`). Production runs on Supabase (use the direct or session-pooler connection, port 5432, because the worker relies on advisory locks and `FOR UPDATE SKIP LOCKED`).
- Queue: a `jobs` table. No Redis, no Celery.
- Guardian: plain code for the policy gate (ten ordered checks), conflict engine, and grounding check. No model can override it.
- Agents: Qualifier, Sequencer, Writer run direct. Researcher and Responder run on DronaHQ through a webhook trigger and MCP tools. Caller runs on DronaHQ Voice. `AGENT_PROVIDER_*` flips any agent between `dronahq` and `direct`.
- Models: `claude-sonnet-5` for Writer and Sequencer plan. `claude-haiku-4-5-20251001` for Qualifier, classifier, verifier, routine follow-ups. All calls go through `agents/llm_client.py`.
- Frontend: static files under `frontend/`, served by FastAPI and embedded in DronaHQ. The page keeps the prototype's render code, reads state from `GET /state` every 3 seconds, and sends every action to the API.
- Shared-secret header for DronaHQ and voice callbacks: `X-Cadence-Secret`, compared in constant time.
- Every channel message carries a `LIVE`, `SANDBOX`, or `REPLAY` badge. Seeded rows carry `is_seed = true` and a `DEMO` chip.

## Engineering rules

- Repo layout follows plan section 15.1. Do not add top-level folders without a reason recorded in `BUILD_STATUS.md`.
- Every campaign-scoped repository function takes `campaign_id` as a required argument.
- Validate every model output with Pydantic. Handle malformed output, timeouts, empty lists, and upstream errors without crashing.
- Use typed exceptions (`GateBlocked`, `AgentFailure`, `ChannelError`, `ConflictDeferred`) and one error envelope: `{"error": {"code", "message", "request_id"}}`.
- Write tests with the feature: unit tests for each gate check, the seven conflict cases, `test_pause_isolation`, Draft refusing a send, the send race, the fake-LLM state machine run.
- `make lint` and `make test` must pass before every commit.
- Commit style: `type(scope): reason` with types `feat`, `fix`, `test`, `docs`, `chore`. One idea per commit. Commit after every working slice.
- No dead code, commented-out blocks, unused endpoints, stray TODOs, placeholder text, lorem ipsum, or fake metrics. Seeded history copies real measured token and cost numbers from test runs.
- Logs are structured JSON. Logs never contain email addresses or message bodies.
- `ALLOWED_RECIPIENTS` gates every email and SMS send. It stays on in production.

## Design rules

- Match the prototype. Keep its typography, spacing, hierarchy, components, and B2B SaaS feel on every screen, including new ones.
- Read `docs/design-system.md` before touching CSS. All tokens live in `frontend/css/tokens.css`. Screens use tokens and shared classes, never one-off values.
- Load the fonts. The prototype declares Onest and IBM Plex Mono and never loads them. Self-host both from `@fontsource/onest` and `@fontsource/ibm-plex-mono` in `frontend/fonts/`.
- No gradients, glow, illustration, or decorative icon. The skeleton shimmer and the hatched bar pattern stay because they carry information.
- New screens and components reuse the existing classes (`.card`, `.tile`, `.tbl`, `.pill`, `.chip`, `.btn`, `.tabs`, `.band`, `.drawer`, `.modal`, `.empty`). Add a new component only when none fits, and document it in `docs/design-system.md`.
- State always pairs color with a word and an icon: Live (green), Paused (amber), Draft (grey), Kill switch (red banner).
- Every screen has designed loading, empty, and error states. Every destructive or global action has a confirmation. Pause offers an undo toast.
- Layout target: 1366 by 768 laptop. Tables scroll inside their own container.

## Definition of done for a feature

1. Code merged with a passing test.
2. Run against the real stack (fake LLM is fine until keys exist) and observed working.
3. UI checked against the prototype with a screenshot at 1366 by 768.
4. `BUILD_STATUS.md` updated with the result, the requirement id it proves (M1 to M19), and the test id.
5. Committed.
