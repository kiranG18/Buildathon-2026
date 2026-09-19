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
