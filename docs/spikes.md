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
