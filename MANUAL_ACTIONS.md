# Manual actions

Claude Code appends to this file and prints a STOP block whenever it needs you. Mark each item done here after you reply "done MA-xx". Never paste a real key into a git-tracked file. Put keys in `.env` locally and in the host's environment settings for production.

Field names inside DronaHQ, Twilio, and Google screens can differ from the text below. Send Claude Code a screenshot of any screen that does not match.

Status: MA-01, MA-02, MA-03, MA-06, MA-07 and MA-10 are done. The app is live at https://buildathon-2026-production.up.railway.app. Still open: the uptime monitor in MA-06, then MA-11 (DronaHQ), MA-04 and MA-05 (keys), MA-08 and MA-09 (Gmail, Twilio), MA-12 (submission). Rotate the Supabase database password and update `DATABASE_URL` on Railway, because it was pasted into a chat.

## MA-01 Local tools (done)

- [x] Python 3.12, Node 22, Docker Desktop and git are installed. Postgres with pgvector runs in Docker on port 5433.
- [ ] Optional: install the GitHub CLI (`gh`) for pull requests. Pushes already work through the stored git credentials.

## MA-02 GitHub repo (done for the code, optional for the team)

- [x] `https://github.com/kiranG18/Buildathon-2026` exists and receives pushes from this machine.
- [ ] Add teammates as collaborators and let each one make a commit, so the history shows every author.
- [ ] Settings, Branches: protect `main` and require the CI checks.

## MA-03 Supabase project (blocks the production deploy)

- [ ] Create a project named `cadence` in the South Asia (Mumbai) region.
- [ ] SQL editor: run `create extension if not exists vector;`
- [ ] Project settings, Database, Connection string: copy the **Direct connection** string, or the **Session pooler** string (port 5432). Skip the Transaction pooler (port 6543).
- [ ] Set it as `DATABASE_URL` on Railway. The web service migrates and seeds an empty database on first start.

## MA-04 Anthropic key (blocks real-model runs)

- [ ] console.anthropic.com, API keys: create `cadence-dev`. Set a monthly spend limit first.
- [ ] Set `ANTHROPIC_API_KEY`, then `LLM_MODE=live`. Models: `claude-sonnet-5` and `claude-haiku-4-5-20251001`.

## MA-05 Embeddings key (blocks real embeddings)

- [ ] Create an API key with an embeddings provider (default model `text-embedding-3-small`, 1536 dimensions) with a spend limit.
- [ ] Set `EMBEDDINGS_API_KEY`. Without it the deterministic local embedder runs.

## MA-06 Hosting on Railway (blocks the public URL)

- [ ] Create a Railway project from the GitHub repo. Choose a plan that never sleeps.
- [ ] Create two services from the same Dockerfile:
  - `web`: the image default start command
  - `worker`: start command `python -m backend.worker`
  - Or one service with `EMBEDDED_WORKER=true`.
- [ ] Generate a public domain for `web` and set it as `BASE_URL`. Set `CORS_ORIGINS` to the same URL and `APP_ENV=production`.
- [ ] Copy every variable you need from `.env.example` into both services. Set `DEMO_MODE=true` for the judged deployment.
- [ ] Add an uptime monitor on `${BASE_URL}/health`, one-minute interval, alert to your phone.

## MA-07 Secrets (blocks the production deploy)

- [ ] Generate three values, store them in a password vault, and set them on both services:

```
python -c "import secrets; print(secrets.token_hex(32))"   # JWT_SECRET
python -c "import secrets; print(secrets.token_hex(32))"   # WEBHOOK_SHARED_SECRET
python -c "import secrets; print(secrets.token_hex(32))"   # MCP_TOKEN
```

The app refuses to start in production with the dev defaults.

## MA-08 Gmail sandbox account and OAuth (blocks live email)

- [ ] Create a dedicated Gmail account for the demo. Set `GMAIL_SENDER` and `SEED_INBOX_BASE` to its address.
- [ ] Google Cloud console: create project `cadence-sandbox`, enable the Gmail API.
- [ ] OAuth consent screen: user type External, publishing status Testing, add the sandbox address as a test user.
- [ ] Add scopes `https://www.googleapis.com/auth/gmail.send` and `https://www.googleapis.com/auth/gmail.readonly`.
- [ ] Credentials: create an OAuth client of type Desktop app. Set `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET`.
- [ ] Get the refresh token: run `GMAIL_CLIENT_ID=... GMAIL_CLIENT_SECRET=... python scripts/gmail_auth.py`, sign in as the sandbox account, and set the printed `GMAIL_REFRESH_TOKEN` on the host.
- [ ] Testing-mode refresh tokens expire after 7 days. Repeat the last step on Sunday before judging.
- [ ] SMTP fallback: turn on 2-step verification, create an app password, set `SMTP_HOST=smtp.gmail.com`, `SMTP_USER`, `SMTP_APP_PASSWORD`.
- [ ] Set `CHANNEL_MODE_EMAIL=live` and `ALLOWED_RECIPIENTS` to the sandbox address or domain.

## MA-09 Twilio (blocks live SMS)

- [ ] Create a trial account and get a trial number. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`.
- [ ] Console, Phone Numbers, Verified Caller IDs: verify one or two team phones.
- [ ] Set the number's inbound SMS webhook to `${BASE_URL}/webhooks/twilio/sms`, method HTTP POST.
- [ ] Add the verified phone numbers to `ALLOWED_RECIPIENTS`, and set `CHANNEL_MODE_SMS=live`.

## MA-10 Source files (done)

- [x] `docs/problem-statement.pdf`, `docs/execution-plan.md` and `frontend/prototype/cadence-prototype.html` are in the repo.

## MA-11 DronaHQ (blocks the hosted agents and Apps Studio). Do these in order and reply "done MA-11a" after each one.

The instruction shells, schemas and app spec are already in `dronahq/` and `agents/schemas/`.

**MA-11a Workspace**
- [ ] Create a workspace. Confirm Apps Studio, the Agentic platform and Voice are enabled. Send a screenshot of the credits meter.

**MA-11b Apps Studio app**
- [ ] Create an app named `Cadence`. Add a REST connector `cadence_api` with base URL `${BASE_URL}` and header `Authorization: Bearer {{jwt}}`.
- [ ] Turn on Public Access. Open the link in a private window and confirm it loads with no DronaHQ login.
- [ ] Add a web or iframe component that embeds `${BASE_URL}/`. Report whether it renders. Then build the native screens from `dronahq/app-spec.md`.

**MA-11c Researcher agent**
- [ ] Create `Cadence Researcher` with variables `campaign_system_prompt`, `agent_prompt`, `context`, `output_schema`. Paste the shell from `dronahq/agents/researcher.md` and the schema `agents/schemas/researcher.json` into Structured Output.
- [ ] Add tools: Web Search, URL Parser, a REST tool `enrich` at `${BASE_URL}/tools/enrich` with header `X-Cadence-Secret: <WEBHOOK_SHARED_SECRET>`, and an MCP server `${BASE_URL}/mcp` (Streamable HTTP, header `Authorization: Bearer <MCP_TOKEN>`).
- [ ] Add a Webhook trigger. Set `DRONAHQ_RESEARCHER_WEBHOOK_URL` and `AGENT_PROVIDER_RESEARCHER=dronahq`. Report whether it answers synchronously and its payload limit.

**MA-11d Responder agent**
- [ ] Repeat MA-11c as `Cadence Responder` with `dronahq/agents/responder.md`, `agents/schemas/responder.json` and the MCP server only. Set `DRONAHQ_RESPONDER_WEBHOOK_URL` and `AGENT_PROVIDER_RESPONDER=dronahq`.

**MA-11e Voice agent**
- [ ] Create a Voice Agent `Cadence Caller` with the script in `dronahq/agents/caller.md`.
- [ ] Pre-call webhook: GET `${BASE_URL}/voice/briefing/{enrollment_id}` with header `X-Cadence-Secret`. Post-call webhook: POST `${BASE_URL}/voice/outcome` with the same header.
- [ ] Place one test call to a verified team phone. Report whether both webhooks fired and the URL and body of the call-start API. Set `DRONAHQ_VOICE_AGENT_ID`, `DRONAHQ_VOICE_CALL_URL` and `CHANNEL_MODE_VOICE=live`.

**MA-11f Evidence**
- [ ] Save screenshots of each agent's instructions, tools and trace to `dronahq/screenshots/` and commit them.

## MA-12 Final submission (blocks P9)

- [ ] Read the submission portal form. Record extra fields, file limits and any earlier cut-off in `docs/submission.md`.
- [ ] Record a backup video from the final build.
- [ ] Submit by 11:00 PM Sunday. Post the social message that tags DronaHQ. Save the confirmation screenshot.
