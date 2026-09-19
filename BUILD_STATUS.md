# Build status

Last updated: Saturday 19 September 2026, 21:30 IST
Current phase: P8 hardening, P9 documents. Waiting on manual actions MA-03, MA-06 and MA-07 (deploy), then MA-04, MA-05, MA-08, MA-09 and MA-11.
Deadline: Sunday 20 September 2026, 11:59 PM IST

## Phases

| Phase | Scope | Status | Gate to pass |
| --- | --- | --- | --- |
| P0 | Inspect repo and references, write implementation plan | done | Built directly from `docs/execution-plan.md` on the user's instruction to skip the plan stop |
| P1 | Repo, Docker, CI, migrations, auth, seed export, first deploy | done except the public deploy | Local `make reset` takes 5 s. The production-mode container boots, migrates, seeds and serves `/health`. Public URL waits on MA-03, MA-06, MA-07 |
| P2 | Worker, gate, conflicts, pause, prompts, lifecycle, reps, `/state` | done | `test_pause_isolation` and the seven conflict cases pass |
| P3 | LLMClient, schemas, RAG, agents, grounding, evals | done offline | 15 of 15 retrieval-and-failure tests pass. Real-model golden runs wait on MA-04 and MA-05 |
| P4 | Frontend wiring and prototype conformance | done | Every route renders from the live API. 9 browser flows with 0 console errors. Screenshots in `docs/screenshots/` |
| P5 | Email live, SMS, LinkedIn sandbox, voice adapter | code done, credentials pending | Adapters tested against mock transports. Real reply landing on the right enrollment waits on MA-08 |
| P6 | MCP server, DronaHQ agents, Apps Studio screens | code done, platform set-up pending | MCP tool call creates a row (tested). DronaHQ side waits on MA-11 |
| P7 | Replay, replanning, analytics, golden-set scores | done | v1 and v2 show different measured scores. LinkedIn pause replans 8 prospects |
| P8 | Hardening, failure injection, security, full test matrix | mostly done | 86 tests pass. Fire drills against the live services wait on the deploy |
| P9 | README, report, deck, demo script, submission | drafted | Live URL, backup video and portal fields wait on MA-06, MA-12 |

## Requirement tracker

| Req | Status | Proof (test id or demo row) |
| --- | --- | --- |
| M1 three concurrent campaigns | done | `test_pause_isolation_three_campaigns`, seeded C1 to C3 Live |
| M2 campaign object with prompts | done | `test_f1_f2_create_campaign_then_activation_needs_the_checklist` |
| M3 prompt versions, isolated | done | `test_f5_i2_prompt_versions_are_stamped_rolled_back_and_isolated` |
| M4 lifecycle, Draft never sends | done | `test_draft_campaign_refuses_a_send` |
| M5 campaign actions and dashboard controls | done | `test_f4_*`, `scripts/ui_flows.py` |
| M6 isolation, duplicates, overlap, conflicts, frequency | done | `tests/conflicts/` K1 to K9 |
| M7 per-campaign dashboard | done | `GET /campaigns/{id}/dashboard`, Campaign Dashboard screen |
| M8 global versus campaign config, suppression | done | `integrations`, `global_settings`, `suppression_list`, gate check 5 |
| M9 prompt UI, version stamped on every action | done | Prompts screen, `agent_runs.prompt_version` |
| M10 four stop levels | done | `test_f4_*`, `test_i4_*`, `test_i5_*`, `test_f12_*` |
| M11 rep assignment and offboarding | done | `test_f9_*` |
| M12 seven named agents | done | `agents/`, seven roles visible in Agent Activity and Prompts |
| M13 per-campaign RAG | done | `test_r1_*`, `test_r2_*` |
| M14 structured output, tools, guardrails, escalation, evals | done | `agents/models.py`, MCP tools, `policy/grounding.py`, `evals/` |
| M15 cost per prospect, per qualified lead, per conversation | done | `test_analytics_numbers_equal_database_counts`. Costs are estimates offline |
| M16 DronaHQ in the core with engineer-written code | code done, hosted set-up pending | `backend/mcp/`, `backend/orchestrator/dronahq.py`, `dronahq/`. Needs MA-11 |
| M17 shared repo, commits from all authors, clean | partial | One author in the history. CI secret scan runs on GitHub |
| M18 malformed output, API failure, empty states | done | `tests/failure/`, error banner and designed empty states |
| M19 report, live URL, repo, deck, demo | partial | Report, deck, demo script written. Live URL and backup video pending |

## Blockers

Waiting for the user (see `MANUAL_ACTIONS.md`): Supabase project, Railway deploy and secrets (MA-03, MA-06, MA-07), then the model and embeddings keys (MA-04, MA-05), Gmail and Twilio (MA-08, MA-09), DronaHQ (MA-11) and the submission (MA-12).

## Next steps

1. MA-03, MA-06, MA-07: deploy on Railway with Supabase, then run the smoke checks in `docs/runbook.md`.
2. MA-11a to MA-11f: DronaHQ workspace, app, three agents, screenshots.
3. MA-04, MA-05 then run the golden sets against the real models and record the real token and cost numbers.
4. MA-08, MA-09: connect Gmail and Twilio and prove EE4.
5. Record the backup video, rehearse `docs/demo.md` twice, submit (MA-12).

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-09-19 | Seed the database from a dump of the prototype's own seed driver (`scripts/dump_prototype.mjs`) | The prototype is the behaviour spec. Reusing its seeded state keeps the demo story identical and removes a large port |
| 2026-09-19 | One `messages` table instead of `outreach` plus `messages`; reps as `users` plus `rep_assignments`; no `analytics_daily` | Same guarantees, fewer moving parts. Listed in `docs/architecture.md` |
| 2026-09-19 | Seeded messages, calls and activity are labelled SANDBOX, and live mode needs a registered adapter | Nothing was actually sent, so no LIVE badge may appear |
| 2026-09-19 | Seeded golden scores are recomputed by the eval runner on every reset | The prototype's scores were invented. No invented metrics |
| 2026-09-19 | The Writer template quality follows the prompt text, not the version number | New campaigns start with the grounded harness as v1 |
| 2026-09-19 | Quota checks take rep and campaign advisory locks, and a campaign's claimed jobs run in score order | Parallel workers exceeded a rep's daily limit, and K7 needs the best prospects first |
| 2026-09-19 | Conflict ties open a conflict row with no winner instead of an approval | The Approvals detail view has no draft to show for a conflict |
| 2026-09-19 | The demo's Dana starts with no queued research job | The Run now moment needs her untouched while the worker is live |
| 2026-09-19 | Pin `mcp<2` | MCP SDK 2.x renamed FastMCP. 1.x is the API this code uses |
| 2026-09-19 | The plan's nine replanned prospects is eight in the seeded data | The prototype's seed leaves Aaron Feld's C1 plan cancelled. The docs say eight |

## Known issues

- The DronaHQ voice call-start URL is a configuration value (`DRONAHQ_VOICE_CALL_URL`), because the call API shape is not verified. MA-11e records the real shape in `docs/spikes.md`.
- Offline agent costs are per-agent list-price estimates. Real usage is recorded in `record` and `live` modes.
- Golden sets are small (15 cases per agent).
- The uptime monitor and the backup video are manual.
