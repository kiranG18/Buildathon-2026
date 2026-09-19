# Test log

Run: 19 September 2026, Windows 11, Python 3.12, Postgres 16 with pgvector in Docker, `LLM_MODE=fake`.

```text
python -m ruff check .        All checks passed
python -m pytest              86 passed in 267 s
python scripts/ui_smoke.py    23 routes rendered at 1366x768, 0 render errors
python scripts/ui_flows.py    9 browser flows, 0 console errors
```

Automated tests run against a real Postgres database (`cadence_test`, rebuilt by the suite). Each row maps a test in the plan's section 17 matrix to the test that proves it.

## Functional and multi-campaign

| Plan id | Test | Result |
| --- | --- | --- |
| F1, F2 | `integration/test_lifecycle_and_controls.py::test_f1_f2_create_campaign_then_activation_needs_the_checklist` | pass |
| F3 | `integration/test_pipeline.py::test_draft_campaign_refuses_a_send` | pass |
| F4 | `test_f4_pause_and_resume_report_held_and_requeued_jobs` | pass |
| F5, I2 | `test_f5_i2_prompt_versions_are_stamped_rolled_back_and_isolated` | pass |
| F6 | `integration/test_replies_and_approvals.py::test_f6_first_touch_approval_approve_sends_reject_sends_nothing` | pass |
| F7 | `test_f7_positive_reply_offers_slots_then_books_a_meeting_and_stops_the_sequence` | pass |
| F8 | `test_f8_unsubscribe_suppresses_every_campaign_and_sends_one_confirmation` | pass |
| F9 | `test_f9_offboarding_lists_affected_campaigns_and_defers_until_reassigned` | pass |
| F10 | `test_f10_daily_cap_defers_the_third_send` | pass |
| F11 | `test_f11_pausing_linkedin_replans_touches_onto_email_with_a_reason` | pass (8 prospects replanned) |
| F12 | `test_f12_kill_switch_holds_every_campaign_and_resume_restores_their_own_state` | pass |
| I1 | `integration/test_pipeline.py::test_pause_isolation_three_campaigns` | pass |
| I4, I5 | `isolation/test_stop_levels.py` | pass |
| K1 to K9 | `conflicts/test_conflicts.py` | pass |
| Gate checks 1 to 10 | `unit/test_gate.py` | pass |
| End to end | `integration/test_pipeline.py::test_dana_runs_from_discovered_to_sent_and_stamps_prompt_version` | pass |

## Agents, RAG, failures

| Plan id | Test | Result |
| --- | --- | --- |
| A2 | `failure/test_llm_failures.py::test_a2_qualifier_never_qualifies_on_invalid_output` | pass |
| A6, MO3 | `test_a6_sequencer_falls_back_to_the_default_sequence_when_the_channel_is_illegal` | pass |
| A7, A8 | `test_a7_*`, `test_a8_*` (live Writer with a scripted transport) | pass |
| A9, A10 | `test_security_questionnaire_escalates_*`, `test_prompt_injection_in_a_reply_*` and the Responder golden set (15 of 15) | pass |
| A11 | `integration/test_dronahq_and_channels.py::test_a11_voice_briefing_and_outcome_webhooks` | pass |
| R1 | `test_r1_ten_retrieval_queries_land_the_expected_chunk_in_the_top_three` | pass (at least 8 of 10) |
| R2 | `test_r2_retrieval_is_campaign_scoped_and_global_chunks_are_shared` | pass |
| R3 | `test_r3_embeddings_down_falls_back_to_full_text` | pass |
| R4 | `test_r4_a_draft_citing_an_unknown_chunk_or_an_unsourced_number_fails_grounding` | pass |
| MO1, MO2, MO5, MO6 | `test_mo1_*`, `test_mo2_*`, `test_mo5_*`, `test_mo6_*` | pass |
| LF1, LF2 | `test_lf1_*`, `test_lf2_*` | pass |
| AF1 | `test_af1_failing_sends_retry_then_escalate_and_three_failures_degrade_the_channel` | pass |
| AF2 | `test_af2_a_dead_dronahq_researcher_falls_back_to_the_direct_provider` | pass |
| AF6 | `test_af6_a_call_without_an_outcome_becomes_unknown_outcome_and_escalates` | pass |

## Security

| Plan id | Test | Result |
| --- | --- | --- |
| AU1 | `test_au1_every_route_needs_a_token_*` | pass |
| AU2, AU3 | `test_rep_cannot_pause_or_flip_the_kill_switch_and_managers_cannot_reset` | pass |
| AU4 | `test_au4_expired_or_tampered_tokens_are_rejected` | pass |
| AU5 | `test_au5_a_wrong_password_and_an_unknown_email_look_identical` | pass |
| SE1 | `test_se1_webhooks_need_the_shared_secret`, `test_twilio_signature_is_verified_*` | pass |
| SE2 | `test_se2_mcp_needs_the_token_and_exposes_exactly_seven_tools` | pass |
| SE4 | `test_prompt_injection_in_a_reply_does_not_change_agent_behaviour` | pass |
| SE5 | `test_se5_sql_injection_in_a_search_parameter_is_inert` | pass |
| SE6 | `test_se6_cors_allows_only_the_configured_origin` | pass |
| SE7 | `test_se7_logs_carry_ids_but_no_email_addresses_or_message_bodies` | pass |
| SE8 | `test_se8_ten_wrong_logins_a_minute_hit_the_rate_limit` | pass |

## Not yet run (waits for a manual action)

| Plan id | Test | Blocked by |
| --- | --- | --- |
| SE3 | `gitleaks` over full history | CI runs it on every push. First result appears on GitHub |
| EE4 | Real email out, real reply in | MA-08 (Gmail) |
| EE5 | Real voice call | MA-11e |
| UI5 | Public link in a private window | MA-11b |
| EE7 | An outsider creates a campaign, edits a prompt and pauses it, unaided | A human tester |
| EE3 | Full demo script twice under seven minutes | Rehearsal on the deployed URL |
| AF3, AF4, AF5 | MCP tool error retry, Twilio unverified number, database timeout | Live services |

## Measured numbers used in the docs

- Seeded golden sets (rule-based, `LLM_MODE=fake`): Qualifier v1 80% and v2 100%, Writer v1 60% and v2 100%, Responder 100% for both versions, for each of C1, C2 and C3. Fifteen hand-labelled cases per agent, five per campaign for the Qualifier and Writer.
- Retrieval: at least 8 of 10 expected chunks in the top three.
- `make reset` finishes in about five seconds with no model or embedding calls.
- The Dockerfile builds, and the production-mode container (`APP_ENV=production` with generated secrets) migrates, seeds an empty database and serves `/health`, `/public/campaigns` and the UI.
