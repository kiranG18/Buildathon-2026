# Build status

Last updated: (fill on every checkpoint)
Current phase: P0
Deadline: Sunday 20 September 2026, 11:59 PM IST

## Phases

| Phase | Scope | Status | Gate to pass |
| --- | --- | --- | --- |
| P0 | Inspect repo and references, write implementation plan | todo | Plan approved by user |
| P1 | Repo, Docker, CI, migrations, auth, seed export, first deploy | todo | `/health` green on public URL, `make reset` under 2 min |
| P2 | Worker, gate, conflicts, pause, prompts, lifecycle, reps, `/state` | todo | `test_pause_isolation` and 7 conflict cases green |
| P3 | LLMClient, schemas, RAG, six agents, grounding, evals | todo | 8 of 10 retrieval queries hit, agent tests A1 to A12 |
| P4 | Frontend wiring and prototype conformance | todo | Every screen renders from live API in all three states and matches the prototype |
| P5 | Email live, SMS, LinkedIn sandbox, voice adapter | todo | Real reply lands on the right enrollment |
| P6 | MCP server, DronaHQ agents, Apps Studio screens | todo | DronaHQ agent calls `save_research`, row appears |
| P7 | Replay, replanning, analytics, golden-set scores | todo | v1 and v2 show different scores |
| P8 | Hardening, failure injection, security, full test matrix | todo | Zero open P0, at most 5 open P1 |
| P9 | README, report, deck, demo script, submission | todo | All links open in a private window |

## Requirement tracker

| Req | Status | Proof (test id or demo row) |
| --- | --- | --- |
| M1 three concurrent campaigns | todo | |
| M2 campaign object with prompts | todo | |
| M3 prompt versions, isolated | todo | |
| M4 lifecycle, Draft never sends | todo | |
| M5 campaign actions and dashboard controls | todo | |
| M6 isolation, duplicates, overlap, conflicts, frequency | todo | |
| M7 per-campaign dashboard | todo | |
| M8 global versus campaign config, suppression | todo | |
| M9 prompt UI, version stamped on every action | todo | |
| M10 four stop levels | todo | |
| M11 rep assignment and offboarding | todo | |
| M12 seven named agents | todo | |
| M13 per-campaign RAG | todo | |
| M14 structured output, tools, guardrails, escalation, evals | todo | |
| M15 cost per prospect, per qualified lead, per conversation | todo | |
| M16 DronaHQ in the core with engineer-written code | todo | |
| M17 shared repo, commits from all authors, clean | todo | |
| M18 malformed output, API failure, empty states | todo | |
| M19 report, live URL, repo, deck, demo | todo | |

## Blockers

None yet.

## Next steps

1. Run P0.

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |

## Known issues

None yet.
