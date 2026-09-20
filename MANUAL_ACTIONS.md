# Manual actions

Claude Code appends to this file and prints a STOP block whenever it needs you. Mark each item done here after you reply "done MA-xx". Never paste a real key into a git-tracked file. Put keys in `.env` locally and in the host's environment settings for production.

Field names inside DronaHQ, Twilio, and Google screens can differ from the text below. Send Claude Code a screenshot of any screen that does not match.

Status: MA-01, MA-02, MA-03, MA-06, MA-07 and MA-10 are done. The app is live at https://buildathon-2026-production.up.railway.app. Still open: the uptime monitor in MA-06, then MA-11 (DronaHQ), MA-04 and MA-05 (keys), MA-08 and MA-09 (Gmail, Twilio), MA-13 (Apollo - company enrichment only, people search is plan-blocked, confirmed live), MA-14 (Hunter + the local LinkedIn finder), MA-12 (submission). Rotate the Supabase database password and update `DATABASE_URL` on Railway, because it was pasted into a chat.

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

## MA-03b Move the database next to the app (optional, makes every page load fast)

Railway runs in Singapore and the first Supabase project is in Mumbai, so each query costs 80 to 150 ms and a rebuilt `/state` takes about 2 s. A database in Singapore brings a query down to a few ms. It also gives a fresh password, which the first one needs because it was pasted into a chat.

- [ ] Supabase: new project `cadence-sg`, region Southeast Asia (Singapore), a letters-and-digits password.
- [ ] SQL editor: `create extension if not exists vector;`
- [ ] Connect, Session pooler: copy the string, put the password in it.
- [ ] `! railway variables set --skip-deploys DATABASE_URL="<string>"`, then `! railway up --detach`. The new service migrates and seeds the empty database by itself, in the same region, so it is quick.

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

**MA-11b Apps Studio app (done, without Public Access)**

Built through the Vibe MCP as app 77710 and published. Public Access needs a licence this workspace does not have, so the public entry point is the Railway link and the DronaHQ app link is extra evidence.
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

## MA-14 Hunter.io and the LinkedIn finder (blocks real employee + email discovery)

Apollo's free plan blocks people search and email reveal entirely (confirmed live, see MA-13). This is the real replacement: find a company's employees on LinkedIn directly (using your own logged-in session, since only your laptop has one - Railway has no browser), then look up each one's real email with Hunter.

**Hunter.io key (optional - the pipeline works fully without it, just with a sandbox placeholder email instead of a verified one)**
- [ ] Sign up at hunter.io if you can (free plan includes a small number of monthly searches). Blocked on 2026-09-20 for this team - hunter.io asked for a professional email address the team didn't have. A personal Gmail sometimes still works; otherwise skip this and ship with the sandbox placeholder.
- [ ] If you do get in: Dashboard, API: copy your API key, set `HUNTER_API_KEY` in `.env` and on both Railway services.
- [ ] Before trusting it, run one real `find_email` call and record the result here and in `docs/spikes.md` - not verified against a live key yet, only that Hunter's documented API shape is what `backend/integrations/hunter.py` expects.

**LinkedIn finder (runs locally only, never on Railway)**
- [ ] Just run it - no separate login step needed. If `.chrome_linkedin_profile/` has no valid session (or it expired), the script itself opens a real, visible Chrome window, waits for you to sign in, saves the session to `.env` and `.chrome_linkedin_profile/`, and continues the same run automatically. (`node scripts/linkedin_login.js` still exists as a standalone one-time login if you'd rather do that first.)
- [ ] From this repo, or downloaded from the live site at `${BASE_URL}/tools/linkedin-finder.js`:
  ```
  node scripts/linkedin_find_employees.js --company "Acme Corp" --domain acme.com --titles "CTO,VP Engineering" --limit 5 \
    --push-to https://buildathon-2026-production.up.railway.app --campaign C1
  ```
  (`--secret` is read from `WEBHOOK_SHARED_SECRET` in `.env` automatically if not passed.)
- [ ] This scrapes LinkedIn's people-search results for the named company and pushes them to `/tools/linkedin-import`, which creates real prospects: real name, title and LinkedIn URL always; a real Hunter-verified email when `HUNTER_API_KEY` is set and Hunter finds one, otherwise a sandbox placeholder address (clearly logged as unverified - never sent to live by accident, since it won't match `ALLOWED_RECIPIENTS`).
- [ ] **Known risk, accepted knowingly**: this automates a personal LinkedIn account's browser session to scrape search results, which is against LinkedIn's terms (same tradeoff `docs/report/report.md` section 6 already documents for the *sending* side - this extends it to search, and the login step now happens inline too). Real risk of that account being restricted or banned. Run it sparingly, and not on an account you can't afford to lose access to.
- [ ] **Safety net**: none of this is required to submit. If it isn't finished by 11 PM, the seeded demo pool (`seed/static.json`: 10/6/4 fresh companies per campaign for on-demand Discover, 40/36/34 in the full pool) and the rehearsed demo cast (`seed/prototype_state.json`, loaded by `make reset`) are completely unaffected by any of tonight's changes and need nothing further.

## MA-13 Apollo.io (company enrichment only - confirmed live against a real free-plan key)

Tested for real against a free-plan key on 2026-09-20:

| Endpoint | Result |
| --- | --- |
| `POST /mixed_people/search` (person search, what `discover()` would use to find people by ICP) | **403** `API_INACCESSIBLE` - "not included in your Free plan... even with a master key" |
| `POST /people/match` (email reveal / person enrichment) | **403**, same reason |
| `GET /organizations/enrich` (company facts for a known domain) | **200** - works |

So on a free plan, `discover()` always falls back to the seeded pool (the search call it would need is blocked), and `/tools/enrich` and `discovery.import_linkedin` (MA-14) get real company facts but no person data from Apollo itself - person data now comes from the LinkedIn finder instead (MA-14).

- [ ] Sign up at apollo.io if you don't already have a key.
- [ ] Set `APOLLO_API_KEY` locally in `.env` and on both Railway services.
- [ ] If you upgrade to a paid plan at any point, `discover()` and `/tools/enrich`'s person-match path activate automatically with no code changes - re-run the two blocked calls above and update this table.
- [ ] `discover()`'s existing cap (max 10 per call) keeps credit use predictable regardless of plan.
