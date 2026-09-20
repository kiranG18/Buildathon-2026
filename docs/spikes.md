# Spikes

Results of the checks the plan schedules for the first hours. A check marked "not yet run" needs an account or a credential and waits for a manual action in `MANUAL_ACTIONS.md`. Nothing here is assumed: each row says what was run.

| # | Check | Result | Evidence |
| --- | --- | --- | --- |
| 1 | MCP server over Streamable HTTP with a bearer header | Pass locally. `initialize`, `tools/list` and `tools/call` work with the token, 401 without | `tests/integration/test_dronahq_and_channels.py::test_se2_*` |
| 2 | Structured Output schema exported from Pydantic | Pass locally. `agents/schemas/*.json` have no `$ref`, so tools that reject references accept them | `make schemas` |
| 3 | Webhook trigger answers synchronously or asynchronously | Both paths are implemented and tested with a mock. The real behaviour is not yet run | MA-11c |
| 4 | Apps Studio REST connector sends a Bearer token from an app variable | Not yet run | MA-11b |
| 5 | Public Access link opens with no login | Not yet run | MA-11b |
| 6 | A list refreshes on a timer in Apps Studio | Not yet run. The embedded static page polls every 3 seconds either way | MA-11b |
| 7 | Voice outbound call reaches a verified phone and both webhooks fire | Webhook handlers tested locally. The real call is not yet run | MA-11e |
| 8 | Gmail send and reply through a plus-addressed inbox | Adapter tested against a mock transport. The real account is not yet connected | MA-08 |
| 9 | Twilio SMS to a verified phone | Adapter and signature check tested. The real account is not yet connected | MA-09 |
| 10 | AI credits cover the demo volume | Not yet run | MA-11a |

## Fallbacks that are already built

| Failure | Fallback in the code |
| --- | --- |
| DronaHQ agent unreachable or silent | Direct provider, `provider_fallback` in the feed |
| Bearer header fails in the connector | The embedded static page carries its own token |
| Gmail OAuth fails | SMTP with an app password, or sandbox |
| Twilio delivery fails | Sandbox handset, `SANDBOX` badge |
| Voice telephony blocked | Scripted call outcome through the same recording path |
| Embeddings down | Full-text retrieval |
| LLM down | Fallback provider, then rules, then `LLM_MODE=replay` |

## Deploy findings (19 Sep 2026)

| Finding | What happened | What to do |
| --- | --- | --- |
| Supabase direct host is IPv6 only | Railway could not reach `db.<ref>.supabase.co` (`Network is unreachable`) | Use the session pooler, `aws-0-<region>.pooler.supabase.com:5432`, user `postgres.<ref>` |
| Seeding across regions is slow | The seed is one transaction of many small calls. From Railway in San Francisco to Supabase in Mumbai it did not finish in minutes, and a stale session held the truncate locks | Run `python scripts/bootstrap.py` once from a machine near the database, or host the web service in the database's region. A second run finds the workspace and starts at once |
| An open seed session blocks every query | While a seed transaction is open, `select count(*) from campaigns` waits and hits the 5 s statement timeout | Wait for it to finish. Do not terminate sessions that look idle in transaction: the seed is working |

## Smoke test of the live deployment (19 Sep 2026)

Target: https://buildathon-2026-production.up.railway.app (Railway, Southeast Asia; Supabase, Mumbai; `LLM_MODE=fake`, `EMBEDDED_WORKER=true`).

| Check | Result |
| --- | --- |
| `GET /health` | 200 |
| `GET /` (UI) | 200 |
| `GET /state` without a token | 401 `no_token` |
| `POST /mcp` without the bearer token | 401 |
| Login as `ava@helix.demo`, then `GET /state` | 4 campaigns: C1 to C3 live, C4 draft. Kill switch off |
| Channel badges on seeded and new messages | all `sandbox` (no live adapter is configured) |
| Worker advancing | queued jobs 8 to 4 and messages 123 to 128 in 45 seconds |
| Error lines in the last 30 log lines | 0 |

## Gmail and Twilio on the live deployment (20 Sep 2026)

| Check | Result |
| --- | --- |
| Gmail OAuth (Web-type client, loopback redirect `http://127.0.0.1:8765/`, Testing mode) | `scripts/gmail_auth.py` returned a refresh token. A Web client needs the redirect URI registered, a Desktop client does not. The sandbox account must be listed as a test user |
| Gmail connection test in the app (`POST /integrations/gmail/test`) | ok |
| First touch to a discovered prospect (`sandbox+name@gmail.com`) | Sent through the Gmail API, recorded as mode `live`, status `sent` |
| Gmail API and `Message-ID` | Gmail replaces the `Message-ID` we set. Replies quote Gmail's, so `send` now reads the assigned id back with a metadata call and stores that. Before this fix no reply matched |
| Poll query | `-from:<sandbox>` had to go: prospects are plus-addresses of the sandbox account, so their replies come from it. Our own copy is skipped by Gmail id and by `Message-ID` |
| Reply from the sandbox mailbox | Matched to the enrollment, classified `book`, and the Responder sent a live email with meeting slots. The prospect moved to `replied_pos` |
| `ALLOWED_RECIPIENTS` and plus-addresses | `name+tag@domain` counts as `name@domain`. Any other address is still refused |
| Twilio connection test in the app | ok (Account SID and Auth Token; an API key is not enough because the webhook signature uses the Auth Token) |

## DronaHQ Vibe MCP (20 Sep 2026)

| Finding | Detail |
| --- | --- |
| Server | `dronahq_mcp`, Streamable HTTP with a bearer token, connected from Claude Code. About 40 `vibe_*` tools (apps, connectors, data agents) and 15 `automation_*` tools. No tool for the Agentic platform agent builder or Voice agents |
| Automations | Task types: REST API, Managed AI, JS Code, Branch, HTTP Response, Delay, Filter, Iterate, connector queries, Call Service (S3, GCS, Lambda, SMTP only). Trigger: WebHook or Scheduler. A webhook automation must not be a bare WebHook to HTTP Response |
| Managed AI | The workspace lists a `DronaHQ_AI` connector (catId 11, no auth) with actions SummarizeText, GenerateText, GenerateChatResponse (input, sysprompt, msgs, temp, model) and GenerateImage. `model` is required and its allowed values are not documented |
| Running the connector | `vibe_run_subcat` on catId 11 fails with "No accounts configured for connector 11". An account has to be added in Studio first. The MCP cannot create one and secrets never go through it |
| Our webhook contract | `backend/orchestrator/dronahq.py`: POST JSON (prompt bundle, prospect context, output schema, optional `api-key` header). The Researcher may answer with facts or save them through our MCP within 90 s. The Responder must answer with classification, reply draft, claims and confidence |

## DronaHQ Apps Studio app (20 Sep 2026)

| Finding | Detail |
| --- | --- |
| App | Vibe app `Cadence`, pluginId 77710, published as version 0.0.1 and set to public access. Source of truth in this repo: `dronahq/app/main.jsx` |
| Screens | Sign in, Command Center with Stop all, campaign list with pause and resume, campaign dashboard with a switch per agent, and the full workspace in a frame. Tested in a real browser against the live API |
| REST connector | `vibe_create_rest_connector` only returns an error that points to the Studio setup link, so a connector cannot be created from the MCP |
| Automation as a proxy | A published automation (webhook, REST API task, HTTP Response task) answered every call, with or without the input schema set, with `{"message":"success"}`. The webhook only acknowledges, so it cannot return the API reply. It was switched off |
| Direct calls | The app calls the API from the browser with a bearer token. `backend/main.py` allows origins matching `https://*.dronahq.com` and refuses everything else (`test_se6_cors_allows_only_the_configured_origin`) |
| Not verified | Whether DronaHQ's runtime allows the app's outbound `fetch` and the framing of the hosted site. This needs a look at the published link in a browser |
| Public access | `vibe_set_access(isPublic: true)` failed with "Secure embed license required". Public embedding of a Vibe app needs a licence the workspace does not have. The app is published but not public, so reviewers cannot open it without a DronaHQ login. The hosted site is the public entry point, and a recording and screenshots show the DronaHQ app |

## First live-model golden run on Groq (20 Sep 2026)

Model: `openai/gpt-oss-120b` (strong role) and `openai/gpt-oss-20b` (fast role) on a free Groq key, through `agents/llm_client.py` with the deterministic mode off. Each case is a real model call. The run was rate-limited, so the Writer numbers below are not a measure of the prompt.

| Role | v1 | v2 | Note |
| --- | --- | --- | --- |
| Responder (C1, C2, C3) | 80%, 87%, 87% | 93%, 87%, 93% | Exact match on the expected classification, 15 cases each |
| Qualifier (C1, C2, C3) | 80%, 60%, 60% | 60%, 80%, 100% | 5 cases each, so one case moves a score by 20 points |
| Writer (C1, C2, C3) | 20%, 0%, 0% | 20%, 20%, 0% | Invalid: Groq's free tier allows about 8,000 tokens a minute and one Writer call uses about 2,100, so most calls returned 429 and the Writer fell back to its generic-safe draft |

Findings:
- Run alone, the Writer produces grounded drafts. Five cases in a row showed two grounded drafts, one draft rejected by the grounding check for an invented number (`207`), which is the check doing its job, and two rate-limit failures.
- The client now waits as long as `Retry-After` asks and asks gpt-oss for low reasoning effort. A second full run with that pacing was started and stopped by the system on low memory, so a clean live Writer score does not exist yet.
- Cost per call was tiny (about $0.00008 for a small classification call at list prices). The prices in the code are unverified.
- The scores in the deck and the Prompts screen come from the deterministic mode until a clean live run exists.

## Live model in production and Twilio (20 Sep 2026)

| Check | Result |
| --- | --- |
| Production on `LLM_PROVIDER=groq`, `LLM_MODE=live` | The LLM integration shows live and OK. One discovered prospect (C1) went from research to qualified (score 72) to a real email in about a minute. The Writer used the model, not the generic-safe fallback, and the proof point cites knowledge chunk K-207 |
| Cost of that prospect in model calls | Qualifier $0.00014, Sequencer $0.00042, Writer $0.0016, at the list prices in `agents/llm_client.py` (unverified prices, real token counts). The Researcher step is a direct enrichment estimate |
| Twilio SMS to an Indian number | Rejected with error 572006, "Invalid template name. Trial accounts can only use predefined SMS templates". A trial account cannot send free text to +91 numbers. The account, credentials and connection test are fine. SMS stays in sandbox unless a verified non-Indian number is available |
