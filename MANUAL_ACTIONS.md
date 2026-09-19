# Manual actions

Claude Code appends to this file and prints a STOP block whenever it needs you. Mark each item done here after you reply "done MA-xx". Never paste a real key into a git-tracked file. Put keys in `.env` locally and in the host's environment settings for production.

Field names inside DronaHQ, Twilio, and Google screens can differ from the text below. Send Claude Code a screenshot of any screen that does not match.

## MA-01 Local tools (blocks P1)

- [ ] Install Python 3.12, Node 20 or newer, Docker Desktop, git, and the GitHub CLI.
- [ ] Install Claude Code, run `claude` in the repo folder, and sign in.

## MA-02 GitHub repo (blocks P1)

- [ ] Create a public repo named `cadence` and add both teammates as collaborators.
- [ ] Settings, Branches: protect `main`, require one pull request approval and passing checks.
- [ ] Each teammate clones the repo and makes at least one commit in P1.

## MA-03 Supabase project (blocks P1 production deploy)

- [ ] Create a project named `cadence` in the South Asia (Mumbai) region.
- [ ] SQL editor: run `create extension if not exists vector;`
- [ ] Project settings, Database, Connection string: copy the **Direct connection** string, or the **Session pooler** string (port 5432). Skip the Transaction pooler (port 6543).
- [ ] Set `DATABASE_URL` locally and on the host.

## MA-04 Anthropic key (blocks P3 real-model tests)

- [ ] console.anthropic.com, API keys: create `cadence-dev`.
- [ ] Set a monthly spend limit before you use it.
- [ ] Set `ANTHROPIC_API_KEY`. Models in use: `claude-sonnet-5` and `claude-haiku-4-5-20251001`.

## MA-05 Embeddings key (blocks P3 RAG tests against the real API)

- [ ] Create an API key with an embeddings provider. Default model: `text-embedding-3-small`, 1536 dimensions.
- [ ] Set `EMBEDDINGS_API_KEY` and a spend limit.

## MA-06 Hosting on Railway (blocks P1 deploy)

- [ ] Create a Railway project from the GitHub repo. Choose a paid plan so the services never sleep.
- [ ] Create two services from the same Dockerfile:
  - `web`, start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
  - `worker`, start command: `python -m backend.worker`
- [ ] Generate a public domain for `web`. Set it as `BASE_URL`.
- [ ] Copy every variable from `.env.example` into both services.
- [ ] Add an uptime monitor (any free monitor) on `${BASE_URL}/health`, one-minute interval, alert to your phone.

## MA-07 Secrets (blocks P1)

- [ ] Run each command once and store the output in the shared password vault.

```
openssl rand -hex 32   # JWT_SECRET
openssl rand -hex 32   # WEBHOOK_SHARED_SECRET
openssl rand -hex 32   # MCP_TOKEN
```

## MA-08 Gmail sandbox account and OAuth (blocks P5 email)

- [ ] Create a dedicated Gmail account for the demo. Set `GMAIL_SENDER` and `SEED_INBOX_BASE` to its address.
- [ ] Google Cloud console: create project `cadence-sandbox`, enable the Gmail API.
- [ ] OAuth consent screen: user type External, publishing status Testing, add the sandbox address as a test user.
- [ ] Add scopes `https://www.googleapis.com/auth/gmail.send` and `https://www.googleapis.com/auth/gmail.readonly`.
- [ ] Credentials: create an OAuth client of type Desktop app. Set `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET`.
- [ ] Run `python scripts/gmail_auth.py` (Claude Code writes it), approve access in the browser, and set `GMAIL_REFRESH_TOKEN`.
- [ ] Testing-mode refresh tokens expire after 7 days. Repeat the last step on Sunday before judging.
- [ ] Set the SMTP fallback: turn on 2-step verification, create an app password, set `SMTP_HOST=smtp.gmail.com`, `SMTP_USER`, `SMTP_APP_PASSWORD`.

## MA-09 Twilio (blocks P5 SMS)

- [ ] Create a trial account and get a trial number. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`.
- [ ] Console, Phone Numbers, Verified Caller IDs: verify 1 or 2 team phones.
- [ ] Set the number's inbound SMS webhook to `${BASE_URL}/webhooks/twilio/sms`, method HTTP POST.
- [ ] Set `ALLOWED_RECIPIENTS` to the team inbox domain and the verified phone numbers, comma separated.

## MA-10 Source files (blocks P0)

- [ ] Copy the problem statement PDF to `docs/problem-statement.pdf` and the plan to `docs/execution-plan.md`.
- [ ] Keep the prototype at `frontend/prototype/cadence-prototype.html`. It is the UI reference, so no separate design files are needed.

## MA-11 DronaHQ (blocks P6). Claude Code prints the exact values when P6 starts.

Do these in order. Reply "done MA-11a" after each one.

**MA-11a Spike and workspace**
- [ ] Create a workspace. Confirm Apps Studio, the Agentic platform, and Voice are enabled. Send a screenshot of the credits meter.

**MA-11b Apps Studio app**
- [ ] Create an app named `Cadence`.
- [ ] Add a REST connector named `cadence_api`. Base URL: `${BASE_URL}`. Header: `Authorization: Bearer {{jwt}}`, where `jwt` is an app variable filled after `POST /auth/login`.
- [ ] Turn on Public Access. Open the link in a private window and confirm it loads with no DronaHQ login.
- [ ] Allow the app to embed `${BASE_URL}/` in a web or iframe component. Report whether it renders.

**MA-11c Researcher agent**
- [ ] Create an agent named `Cadence Researcher`. Add variables `campaign_system_prompt`, `agent_prompt`, `context`, `output_schema`.
- [ ] Paste the instructions from `dronahq/agents/researcher.md` (Claude Code writes it).
- [ ] Turn on Structured Output and paste `agents/schemas/researcher.json`.
- [ ] Add tools: Web Search, URL Parser, and a REST tool `enrich` at `${BASE_URL}/tools/enrich` with header `X-Cadence-Secret: ${WEBHOOK_SHARED_SECRET}`.
- [ ] Add an MCP server: URL `${BASE_URL}/mcp`, transport Streamable HTTP, header `Authorization: Bearer ${MCP_TOKEN}`.
- [ ] Add a Webhook trigger. Set `DRONAHQ_RESEARCHER_WEBHOOK_URL` to its URL. Report whether it answers synchronously and the payload limit.

**MA-11d Responder agent**
- [ ] Repeat MA-11c with the name `Cadence Responder`, instructions from `dronahq/agents/responder.md`, schema `agents/schemas/responder.json`, and the MCP server only. Set `DRONAHQ_RESPONDER_WEBHOOK_URL`.

**MA-11e Voice agent**
- [ ] Create a Voice Agent named `Cadence Caller` with the script in `dronahq/agents/caller.md`.
- [ ] Pre-call webhook: GET `${BASE_URL}/voice/briefing/{enrollment_id}` with header `X-Cadence-Secret: ${WEBHOOK_SHARED_SECRET}`.
- [ ] Post-call webhook: POST `${BASE_URL}/voice/outcome` with the same header.
- [ ] Place one test call to a verified team phone. Report whether both webhooks fired. Set `DRONAHQ_VOICE_AGENT_ID`.

**MA-11f Evidence**
- [ ] Save screenshots of each agent's instructions, tools, and trace to `dronahq/screenshots/` and commit them.

## MA-12 Final submission (blocks P9)

- [ ] Read the submission portal form. Record extra fields, file limits, and any earlier cut-off in `docs/submission.md`.
- [ ] Submit by 11:00 PM Sunday. Post the social message that tags DronaHQ. Save the confirmation screenshot.
