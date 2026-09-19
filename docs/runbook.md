# Runbook

## Services

| Service | Command | Notes |
| --- | --- | --- |
| web | `sh -c "python scripts/bootstrap.py && uvicorn backend.main:app --host 0.0.0.0 --port $PORT"` (the image default) | Applies migrations, loads the demo workspace into an empty database, serves the API and the UI |
| worker | `python -m backend.worker` | Claims jobs, polls Gmail, sweeps voice outcomes. Set the same environment variables as web |
| single service | web with `EMBEDDED_WORKER=true` | Simplest shape for a small host. Two services is the recommended one |

Health: `GET /health` returns 200 with `{"status": "ok"}`. Point an uptime monitor at it with a one-minute interval.

## Deploy on Railway with Supabase

Manual steps are `MANUAL_ACTIONS.md` MA-03, MA-06 and MA-07. After they finish, confirm `/health` on the public URL, sign in with a demo chip, and run `python scripts/check_env.py` in the service shell.

## Reset

`python scripts/reset_demo.py` (or `make reset`) drops the schema, migrates and reloads the demo workspace in about five seconds, including golden-set scores. It never calls a model or an embedding API. Admins can also use Settings, Demo tools, Reset data.

## Failure drills

Break each of these once before the demo and confirm the recovery:

| Drill | How | Expected |
| --- | --- | --- |
| DronaHQ down | Point `DRONAHQ_RESEARCHER_WEBHOOK_URL` at a dead host | The step reruns on the direct provider and the feed shows `provider_fallback` |
| Gmail revoked | Clear `GMAIL_REFRESH_TOKEN` | The channel falls back to sandbox and badges say `SANDBOX`. Settings shows the error on Test connection |
| Embeddings down | Set `FAIL_EMBEDDINGS=1` | Retrieval answers from full-text search |
| LLM key invalid | Set a bad `ANTHROPIC_API_KEY` with `LLM_MODE=live` | Retries, fallback, then rules. Nothing qualifies on failure |
| LLM output garbage | `FAIL_LLM=garbage` | One repair pass, then a handled failure |
| Channel down | `FAIL_CHANNEL=email` | Retries, an escalation, and the channel shows an error after three failures |
| Network down | Switch to the phone hotspot | The UI shows the reconnect banner and resumes |
| Cold replay | `LLM_MODE=replay` | Recorded outputs serve the demo cast. Affected runs show a REPLAY badge |

## Operating notes

- Prompt changes apply to the next job. Running jobs finish on the old version.
- A held job stays `queued` and shows as `held` while its campaign is paused, its agent is off, or the kill switch is on.
- To isolate one campaign in its own process, set `WORKER_CAMPAIGN_ID`.
- Logs are structured JSON with `request_id`, `campaign_id`, `job_id` and `agent`. They carry no email addresses or message bodies.
- Rotate a leaked key first, then investigate.
