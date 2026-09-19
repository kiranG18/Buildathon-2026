# Claude Code prompts for the Cadence build

## Setup (15 min)

1. Create the repo folder and copy this kit into it (`CLAUDE.md`, `BUILD_STATUS.md`, `MANUAL_ACTIONS.md`, `PROMPTS.md`, `.claude/`).
2. Add the source files:
   - `docs/problem-statement.pdf`
   - `docs/execution-plan.md`
   - `frontend/prototype/cadence-prototype.html` (the UI reference and behavior spec, already in this kit)
3. Run `git init` (or clone your GitHub repo) and commit the kit.
4. Add browser control for UI review: `claude mcp add playwright -- npx @playwright/mcp@latest`. Run `/mcp` inside Claude Code and confirm it lists `playwright`.
5. Run `/permissions` and allow the routine commands so the build does not stall on prompts: `Bash(make:*)`, `Bash(pytest:*)`, `Bash(ruff:*)`, `Bash(python:*)`, `Bash(node:*)`, `Bash(npm:*)`, `Bash(docker compose:*)`, `Bash(git add:*)`, `Bash(git commit:*)`. Leave `git push`, `rm`, and anything that touches production on ask.
6. Run `/model` and choose the strongest model available.
7. Start P0 in plan mode (`/plan`).

## Session habits

- Start each phase with `/clear`. `BUILD_STATUS.md` holds the state, so a fresh context costs nothing.
- Open every phase with: `Read CLAUDE.md and BUILD_STATUS.md, then run the phase below.`
- Run `/checkpoint <slice>` after every working slice and `/ui-review <screens>` after every UI change.
- Run `/context` when a session feels slow. Run `/compact` before the window fills.
- Parallel work after P1 (optional): `git worktree add ../cadence-ai -b ai/work` and `git worktree add ../cadence-ui -b ui/work`. Run P2, P3, and P4 in three sessions and merge through pull requests. P1 publishes the `/state` contract so P4 can build against a fixture.

## Kickoff prompt (paste first, in plan mode)

```
You are the lead engineer for Cadence. Build the product end to end. Write the code, run it, test it, and fix it. Do not stop at explanations.

Read CLAUDE.md first, then read every source of truth in the order it lists. The problem statement defines functionality and judging. The prototype defines the UI language (BizLink B2B SaaS): keep its typography, spacing, hierarchy, components, and feel on every screen. Rank a working end-to-end MVP above extra features. Every screen and interaction must do real work. No placeholders, no decorative components, no gradients, no generic AI aesthetics.

Follow this loop for every feature: Plan, Build, Run, Test, Fix, UI review against the prototype, update BUILD_STATUS.md, commit.

For anything I must do by hand (DronaHQ setup, API keys, OAuth, external integrations, deployment, account settings), follow the Manual stop protocol in CLAUDE.md: write the exact steps and values to MANUAL_ACTIONS.md, print a STOP block, and wait for my reply.

Start with Phase P0 below. Do not write product code until I approve the plan.
```

## P0: Inspect and plan

```
Phase P0. Write no product code.

1. Read CLAUDE.md, docs/problem-statement.pdf, docs/execution-plan.md, docs/design-system.md, frontend/css/tokens.css, and the prototype.
2. Open the prototype in Playwright, log in, and dump the JavaScript state object `S` to seed/prototype_state.json. List every `ACT.*` handler and the API endpoint it will call.
3. Write docs/IMPLEMENTATION_PLAN.md:
   - A gap table: each requirement M1 to M19 against the plan and the prototype (covered, partial, missing).
   - The ordered task list per phase P1 to P9 with time boxes that fit the deadline in CLAUDE.md.
   - The manual steps per phase, matched to MANUAL_ACTIONS.md.
   - Risks and the fallback for each.
4. Check docs/design-system.md against the prototype's CSS and correct any value that differs.
5. Update BUILD_STATUS.md and MANUAL_ACTIONS.md. List every question you need answered.
6. End your turn and wait for approval.
```

## P1: Foundation and first deploy

```
Phase P1.

Build:
1. Repo layout from plan section 15.1, Makefile (dev, db, seed, reset, test, lint, schemas), Dockerfile, docker-compose.yml with pgvector/pgvector:pg16, .env.example with every variable in plan section 15.3, .gitignore, pyproject.toml, CI (ruff, pytest, gitleaks), CODEOWNERS, PR template.
2. Migrations 001 to 004 from plan section 3.7 with the constraints in CLAUDE.md and the plan: one active prompt per (campaign, agent), one active claim per prospect, unique enrollment per (campaign, prospect), unique idempotency key on outreach, HNSW and GIN indexes.
3. backend/core: config (fail fast on missing variables), db, security (JWT, roles admin/manager/rep), logging (structured JSON with request_id), error envelope, demo clock.
4. Routes: /health, POST /auth/login with the five seeded users.
5. scripts/load_seed.py: map seed/prototype_state.json into tables with timestamps as offsets from the demo clock, write knowledge files to knowledge/ with frontmatter, prompts to seed/prompts/. make reset must finish in under 2 minutes and restore the demo state.
6. docs/state-contract.md and a Pydantic StateResponse model that mirrors the prototype's `S` (camps, users, people, enr, msgs, acts, jobs, approvals, escal, conflicts, meetings, calls, claims, suppress, prompts, kb, integ, kill, now). Add a stub GET /state that serves the seed fixture so the UI can start.

Test: login for each role, role checks return 403 where they should, reset three times, seed counts match the plan (3 Live, 1 Draft, 90 prospects).

Manual stops: MA-01, MA-02, MA-03, MA-06, MA-07. Develop on local Docker until MA-03 is done. After MA-06, deploy and confirm /health on the public URL.
Exit gate: /health green on the public URL, all three authors have commits, BUILD_STATUS.md updated.
```

## P2: Backend core

```
Phase P2. Port the prototype's logic to Python. Use the prototype as the spec.

Build in this order, with tests alongside:
1. Job queue and worker: FOR UPDATE SKIP LOCKED, 2-second poll, cap 3 jobs per campaign, only Live campaigns, per-job try/except, retries at 30 s, 2 min, 10 min, then an agent_failure escalation. Use a fake agent runner until P3.
2. Enrollment state machine and job types from plan section 3.3.
3. Policy gate with the ten ordered checks, reason codes, idempotency key, advisory lock, and one transaction for the frequency check plus the outreach insert. Port gateEval.
4. Conflict engine: contact_claims, the seven-rule ladder, resolve_claim, conflict rows, manager approval on a tie. Port ladder, resolveClaim, addConflict.
5. Pause semantics, agent and channel toggles, kill switch, resume that re-queues held jobs.
6. Lifecycle and pre-launch checklist (Activate returns 409 with failing checks), dry run endpoint, duplicate as variant.
7. Prompt versions API: save, diff, atomic activate, roll back, audit event, version stamped on every agent_runs row.
8. Reps: assignments, limits, hours, offboard, reassign, no_rep_available deferral.
9. Every remaining endpoint in plan section 16, and the real GET /state that returns the StateResponse shape.

Tests to write: test_pause_isolation, conflict cases K1 to K9, F3 Draft refuses a send, K8 send race, one unit test per gate check, tenant isolation I2 to I5, full state machine run with LLM_MODE=fake.
Exit gate: make test is green and three fake campaigns run concurrently with a working pause.
No manual stops in this phase.
```

## P3: AI layer

```
Phase P3.

Build:
1. agents/llm_client.py: one run(agent, prompt_version, context, schema) method. 30-second timeout, two retries with backoff, JSON parse, Pydantic validation, one repair pass, fallback provider, rule-based default, cost and latency logging. Modes: LLM_MODE=fake, record, replay.
2. agents/models.py with the six output models, JSON Schemas exported to agents/schemas/ (researcher.json and responder.json are pasted into DronaHQ later), six-part prompt renderer, ProspectMemory builder with a 3,000-token budget.
3. rag/: chunking rules from plan section 3.6, ingest with cached embeddings, hybrid retrieval (vector top 20 plus full-text top 20, reciprocal rank fusion, filter on campaign_id or global scope), citation ids, POST /knowledge/search. Use a deterministic local embedder when no key exists so tests run offline.
4. Agents: Qualifier (hard filters in code, model judges criteria, code computes the score), Sequencer (plan and next_step, code lists allowed channels, validates the pick, falls back to the default sequence), Writer (claims[], grounding check ported from groundCheck, one regeneration, generic_safe variant), Responder (rules first for unsubscribe, out-of-office, bounce, then classification, escalation triggers), Researcher direct provider with the enrichment stub reading seed facts and /demo-sources/ pages.
5. evals/: 15 golden cases each for Qualifier, Responder, Writer (LLM judge at temperature 0), runner, results in eval_runs.
6. Replay: input_snapshot on every run and POST /agent-runs/{id}/replay.

Test: A1 to A12, R1 to R5, MO1 to MO6, LF1 to LF3 with injected failures.
Manual stops: MA-04 and MA-05 before any real-model run. After both, run the golden sets, run the four hero prospects five times, tune prompts until five of five pass, record replay fixtures, and log real token and cost numbers.
Exit gate: 8 of 10 retrieval queries land in the top 3, 90 percent of Writer drafts pass grounding, missing facts produce no invented claim.
```

## P4: Frontend wiring and prototype conformance

```
Phase P4.

Build:
1. Split the prototype into frontend/index.html, frontend/css/tokens.css (already provided), frontend/css/app.css, and frontend/js/*.js modules with no bundler.
2. Self-host Onest and IBM Plex Mono (`npm i @fontsource/onest @fontsource/ibm-plex-mono`, copy the woff2 files to frontend/fonts/, add @font-face rules). Apply the fixes listed at the end of docs/design-system.md. Move inline styles from the render code into token-based classes. The look must stay identical to the prototype.
3. Add frontend/js/api.js: token handling, call() helper with the error banner ("Cannot reach the server. Retrying in 5 seconds"), hydrate() that reads GET /state every 3 seconds into S and repaints when the signature changes.
4. Rewrite every ACT.* handler to call its endpoint and then hydrate. Delete the in-browser engine (tick, runJob, gateEval, resolveClaim, ladder, doResearch, doQualify, doPlan, doDraft, compose, classify, groundCheck, advanceClock, seed functions). Keep only read-only render helpers.
5. Add what the prototype lacks: Run now on Prospect Detail, Play scripted call outcome in Demo tools, campaign switcher in the top bar, REPLAY badge beside LIVE and SANDBOX, role-based hiding backed by API 403s.
6. Give every screen loading, empty, and error states. Serve the frontend from FastAPI at /.

Test: stop the API and open every screen (UI1), pause a campaign and watch the counters (UI2, UI6), kill switch banner on every screen (UI3), feed updates within 3 seconds (UI4), each demo role sees the right navigation (UI6).
Run /ui-review for every route and fix deviations until none of high impact remain.
Exit gate: every screen renders from the live API in all three states and matches the prototype.
```

## P5: Channels

```
Phase P5.

Build the Channel interface with capabilities(), send(), poll_inbound(). Then:
1. Email on Gmail API: send with Message-ID, thread by In-Reply-To, poll every 30 seconds, SMTP fallback, sandbox mode.
2. SMS on Twilio with signature verification on /webhooks/twilio/sms.
3. LinkedIn sandbox adapter with a mock inbox and simulated acceptance.
4. Voice adapter that triggers the DronaHQ Voice agent, plus /voice/briefing and /voice/outcome.
5. One ingest_reply function for Gmail polling, Twilio, the simulator, and the voice post-webhook. Unsubscribe, out-of-office, and bounce rules run before any model call.
6. ALLOWED_RECIPIENTS enforced in every adapter. LIVE, SANDBOX, or REPLAY on every message.
7. scripts/gmail_auth.py for the OAuth flow.

Manual stops: MA-08, MA-09.
Test: EE4 (real email out, real reply in, correct enrollment and classification), AF1, AF4, AF6, F8 (unsubscribe stops every campaign).
Exit gate: a real reply lands on the right enrollment.
```

## P6: MCP server and DronaHQ

```
Phase P6.

Build:
1. backend/mcp/: MCP server at /mcp over Streamable HTTP with bearer token auth and exactly seven tools (search_knowledge, get_timeline, save_research, propose_slots, book_meeting, create_escalation, set_classification).
2. dronahq/agents/researcher.md, responder.md, caller.md (generic instruction shells with the four variables), dronahq/README.md, dronahq/app-spec.md listing each native Apps Studio screen with its endpoint bindings and refresh behavior, dronahq/vibe-prompts.md.
3. Worker to DronaHQ webhook payload from plan section 16.11, callback handling, 90-second timeout that reruns on the direct provider, AGENT_PROVIDER_* flags.
4. The /tools/enrich REST tool.

Manual stop: MA-11a to MA-11f, one at a time. After each reply, run the matching verification: webhook returns structured output, MCP tool call creates a row, voice webhooks fire. Record every result in docs/spikes.md and switch to the plan section 20.2 fallback for any failure.
Test: AF2, AF3, A11, SE1, SE2, plus a trace where the DronaHQ agent calls save_research and the same event shows in activity.
Exit gate: a DronaHQ Researcher run saves sourced facts through MCP, and the flag flip to direct also works.
```

## P7: Measurement and standout features

```
Phase P7.

Build:
1. Analytics endpoints and screen: cost per prospect, per qualified lead, per conversation, reply rate, positive-reply rate, meeting rate, cost by agent, prompt-version table.
2. Replay drawer in the trace view (P1 feature).
3. Live replanning: channel, rep, or reply changes enqueue debounced plan jobs, old and new plan stored in activity.payload, feed event "Replanned N prospects".
4. Eval scores on the Prompts screen for v1 and v2.
5. Check the cost targets from real agent_runs: under $0.05 per rejected prospect and under $0.40 per qualified lead. Report the real numbers.

Test: F11, analytics numbers equal database counts, EE2.
Exit gate: v1 and v2 show different golden-set scores and the replan event appears after a LinkedIn pause.
```

## P8: Hardening

```
Phase P8.

1. Failure injection: FAIL_LLM=garbage and timeout, FAIL_EMBEDDINGS=1, FAIL_CHANNEL=email. Each ends in a handled state with a log line.
2. Security: AU1 to AU5, SE1 to SE8, CORS allowlist, rate limits, gitleaks over full history, prompt-injection test SE4.
3. Run the full test matrix in plan section 17. Log results in docs/test-log.md.
4. Run the must-run list in plan section 17.7 against production.
5. make reset three times. Fire drills from plan section 20.4.
6. Remove dead code with ruff and vulture. Resolve every TODO or turn it into an issue.

Exit gate: zero open P0, at most five open P1, /health green, spare service on the other host running the latest tag.
```

## P9: Deliverables

```
Phase P9.

1. README with the 12 items in plan section 15.5, tested from a clean clone.
2. docs/architecture.md with the Mermaid diagram, docs/api.md, docs/openapi.json, docs/runbook.md.
3. Report in docs/report/ with the requirement map (M1 to M19) and a proof column filled from BUILD_STATUS.md.
4. Deck outline and slide text in docs/deck/ (12 slides plus the judge card). Numbers come from agent_runs, eval_runs, and docs/test-log.md.
5. docs/demo.md with the click-by-click script and the recovery lines.
6. Run the production checklist in plan section 21.3 and the repo rules in section 22.2.

Manual stop: MA-12.
Exit gate: every submission link opens in a private window.
```

## Recovery prompts

Tests fail twice:
```
Stop coding. Read the failing test and the code it covers. State the root cause in two sentences. Fix the cause, add a regression test, and run make test.
```

Context is full or the session drifted:
```
/clear
Read CLAUDE.md and BUILD_STATUS.md. Continue the current phase from the first unchecked item.
```

A DronaHQ or channel spike fails:
```
Open plan section 20.2. Apply the fallback for this item, record the decision in docs/spikes.md and BUILD_STATUS.md, then continue with the fallback path and a visible badge.
```

Behind schedule:
```
Apply the next cut level from plan section 13.5. List what you cut, which requirement each cut touches, and how the thinner version still satisfies it.
```

## Pace

| Phase | Serial hours | Ready by |
| --- | --- | --- |
| P0 | 0.5 | Start |
| P1 | 2 | After P0 approval |
| P2, P3, P4 | 5 each, parallel if you run three sessions | After P1 |
| P5 | 3 | After P2 |
| P6 | 4 | After P3 and MA-11 |
| P7 | 3 | After P6 |
| P8 | 4 | Sunday 6 PM feature freeze |
| P9 | 4 | Sunday 9 PM deploy freeze |

Run P2 to P4 in parallel sessions if you can. Serial execution of P0 to P7 leaves no room before the freeze.
