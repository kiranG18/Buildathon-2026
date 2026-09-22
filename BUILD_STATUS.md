# Build status

Last updated: Sunday 20 September 2026, 9 PM (deploy freeze)
Current phase: submission. Live at https://buildathon-2026-production.up.railway.app (Railway, Singapore; Supabase Postgres, Mumbai). The workspace is empty and every campaign is archived.
Deadline: Sunday 20 September 2026, 11:59 PM IST. Feature freeze 6 PM, deploy freeze 9 PM, submit by 11 PM.

## Phases

| Phase | Scope | Status | Gate to pass |
| --- | --- | --- | --- |
| P0 | Inspect repo and references, write implementation plan | done | Built directly from `docs/execution-plan.md` |
| P1 | Repo, Docker, CI, migrations, auth, seed export, first deploy | done | Live URL, smoke test in `docs/spikes.md` |
| P2 | Worker, gate, conflicts, pause, prompts, lifecycle, reps, `/state` | done | `test_pause_isolation` and the seven conflict cases pass |
| P3 | LLMClient, schemas, RAG, agents, grounding, evals | done | Three providers (Anthropic, Gemini, Groq) behind one client. Real-model golden runs recorded in `docs/spikes.md` once complete |
| P4 | Frontend wiring and prototype conformance | done | Every route renders from the live API, 0 console errors |
| P5 | Email live, SMS, LinkedIn, voice | email live and proven; LinkedIn rep-assisted; SMS and voice sandbox | A discovered prospect got a real email, a reply was matched, classified and answered. Twilio rejects free-text SMS to India (572006). Voice needs an outbound number in DronaHQ |
| P6 | MCP server, DronaHQ agents, Apps Studio screens | done except live voice calls | Native app 77710 published. The hosted Researcher and Responder run in production and are traced in `docs/spikes.md` |
| P7 | Replay, replanning, analytics, golden-set scores | done | v1 and v2 show different measured scores |
| P8 | Hardening, failure injection, security, full test matrix | done | Full suite green in CI, CORS locked to dronahq.com origins, row level security on every table |
| P9 | README, report, deck, demo script, submission | done except the portal form | Report, deck and README refreshed. The submission form and the DronaHQ post remain |

## Requirement tracker

| Req | Status | Proof (test id or demo row) |
| --- | --- | --- |
| M1 three concurrent campaigns | done | `test_pause_isolation_three_campaigns`, seeded C1 to C3 Live |
| M2 campaign object with prompts | done | `test_f1_f2_create_campaign_then_activation_needs_the_checklist` |
| M3 prompt versions, isolated | done | `test_f5_i2_prompt_versions_are_stamped_rolled_back_and_isolated` |
| M4 lifecycle, Draft never sends | done | `test_draft_campaign_refuses_a_send` |
| M5 campaign actions and dashboard controls | done | `test_f4_*`, `scripts/ui_flows.py`, the DronaHQ app |
| M6 isolation, duplicates, overlap, conflicts, frequency | done | `tests/conflicts/` K1 to K9 |
| M7 per-campaign dashboard | done | `GET /campaigns/{id}/dashboard`, Campaign Dashboard screen, DronaHQ app |
| M8 global versus campaign config, suppression | done | `integrations`, `global_settings`, `suppression_list`, gate check 5 |
| M9 prompt UI, version stamped on every action | done | Prompts screen, `agent_runs.prompt_version` |
| M10 four stop levels | done | `test_f4_*`, `test_i4_*`, `test_i5_*`, `test_f12_*` |
| M11 rep assignment and offboarding | done | `test_f9_*` |
| M12 seven named agents | done | `agents/`, seven roles visible in Agent Activity and Prompts |
| M13 per-campaign RAG | done | `test_r1_*`, `test_r2_*` |
| M14 structured output, tools, guardrails, escalation, evals | done | `agents/models.py`, MCP tools, `policy/grounding.py`, `evals/` |
| M15 cost per prospect, per qualified lead, per conversation | done | `test_analytics_numbers_equal_database_counts`. Costs are measured only in live model mode |
| M16 DronaHQ in the core with engineer-written code | done except live voice calls | Native Apps Studio app, hosted Researcher (saves facts through `save_research`) and hosted Responder (submits decisions through `set_classification`), both in production with fallback to the direct provider. |
| M17 shared repo, commits from all authors, clean | partial | One author in the history. CI secret scan runs on GitHub |
| M18 malformed output, API failure, empty states | done | `tests/failure/` including 429 handling |
| M19 report, live URL, repo, deck, demo | partial | Live URL, report, deck and demo script done. Backup video and submission pending |

## Blockers

Waiting for the user: rotating the pasted secrets, changing the seeded account passwords, an outbound phone number on the DronaHQ Voice agent, the submission form and the DronaHQ post.

## Next steps

1. Submit before 11 PM with credentials on the portal form.
2. Optional after judging: move the database to Singapore, run a clean live-model golden set.

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-09-19 | Seed the database from a dump of the prototype's own seed driver | The prototype is the behaviour spec |
| 2026-09-19 | One `messages` table instead of `outreach` plus `messages`; reps as `users` plus `rep_assignments` | Same guarantees, fewer moving parts |
| 2026-09-19 | Seeded messages, calls and activity are labelled SANDBOX, and live mode needs a registered adapter | Nothing was actually sent |
| 2026-09-19 | Seeded golden scores are recomputed by the eval runner on every reset | The prototype's scores were invented |
| 2026-09-19 | Quota checks take rep and campaign advisory locks | Parallel workers exceeded a rep's daily limit |
| 2026-09-19 | Pin `mcp<2` | MCP SDK 2.x renamed FastMCP |
| 2026-09-20 | Use the Supabase session pooler, seed from a machine near the database | The direct host is IPv6 only. Seeding across regions is slow |
| 2026-09-20 | Serve `/state` from memory until a one-query signature changes | 168 queries per call across regions took 14 seconds |
| 2026-09-20 | A recipient off `ALLOWED_RECIPIENTS` is recorded as a sandbox send | A refusal is not a channel outage |
| 2026-09-20 | Gmail replies match by the Message-ID Gmail assigns, and the whole inbox is polled | Gmail replaces the Message-ID we set, and prospects are plus-addresses of the sender |
| 2026-09-20 | The DronaHQ app calls the API directly, and the API allows dronahq.com origins only | A DronaHQ webhook only acknowledges a call, and a REST connector needs a Studio link |
| 2026-09-20 | Add Gemini and Groq providers | The team has no Anthropic API key, only a chat subscription |
| 2026-09-20 | Wait as long as a provider's Retry-After says on a 429 | Groq's free tier allows about 8,000 tokens a minute |
| 2026-09-22 | Google Sheets CRM mirror pushes every enrollment via a service-account JWT bearer flow (no OAuth consent screen), overwrite-not-diff, called from the worker's existing maintenance tick | Judge-facing request for a spreadsheet view of the CRM, added post-deadline-extension; service account needs only "share with this email", no user sign-in |
| 2026-09-22 | Permanent campaign delete (`DELETE /campaigns/{id}`) only accepts an already-archived campaign, is Admin-only, and erases every dependent row in one transaction (enrollments, messages, jobs, approvals, escalations, meetings, calls, eval_runs, campaign_versions, suppression rows, and it strips the id out of any `conflicts.campaign_ids` array) | Archived campaigns were invisible everywhere in the UI with no way to reclaim the row; deleting only from `archived` means nothing in flight is ever lost |
| 2026-09-22 | `/state`'s own signature is no longer cached, only the rebuilt state is (`backend/api/state.py`); the `enrollments` hash now includes `rep_id` | A rep reassignment (new inline picker on a prospect's page) wrote to the database correctly but `/state` kept serving the pre-reassignment snapshot: the 1s `SIG_CACHE_TTL` on the signature itself meant a write inside that window went undetected regardless of what the signature's SQL covered, and `rep_id` was missing from that SQL besides. Fixing both also fixes `test_state_is_served_from_memory_until_something_changes`, previously flaky for the same reason |

## Known issues

- The Twilio trial rejected the first real text with a 400. SMS stays in sandbox until a verified number works.
- Live-model golden scores depend on the provider's rate limit. The first run scored the Writer near 0% because of 429s, and it was rerun with pacing.
- Public Access on the DronaHQ app needs a licence the workspace does not have.
- Gemini and Groq prices in `agents/llm_client.py` are entered by hand and unverified.
- Cross-region latency: each database query costs about 80 to 150 ms.
- Two CI runs failed earlier on an intermittent test that was not identified. Later runs pass.
- The Sheets CRM mirror is one-way (Cadence to Sheets) and a full overwrite, not a diff; a manual edit in the sheet is silently overwritten on the next sync.
