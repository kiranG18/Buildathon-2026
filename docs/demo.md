# Demo script

Seven minutes. It proves the statement's requirements in order: three concurrent campaigns, agents doing real work, one live pause that leaves the other campaigns running, and the controls behind it. A five-minute cut follows. Every step names the rubric category it earns.

## Staging

- One person drives the app signed in as Ava Chen (manager). A second person drives the DronaHQ agent-builder tab, the Gmail tab and the phone. A third watches logs and runs `make reset` afterwards.
- Tabs in order: (1) the Cadence app, (2) the Gmail seed inbox, (3) the DronaHQ agent builder on the Researcher, (4) the backup video.
- Demo cast (all fictional, all labelled `DEMO`): Dana Whitfield (C1, untouched), Tomas Reyes (C1, emailed and silent), Rajiv Menon (C2), Noor Haddad (C3), Sam Okafor (in C1 and C3).
- Say `SANDBOX` aloud whenever a sandbox badge appears. A channel without credentials runs in sandbox and says so.

## Click by click

| Time | Open or click | Say | The system does | Category |
| --- | --- | --- | --- | --- |
| 0:00 | Command Center | "Cadence is an autonomous SDR with a manager control plane. Three campaigns run now, each with its own ICP, prompts and channels." | Feed streams events from all three campaigns, colour-tagged | Product, DronaHQ |
| 0:30 | C1 Prompts tab, then C3 Prompts tab | "C1 sells to US SaaS CTOs: email first, concise, technical. C3 targets voice AI founders: casual, LinkedIn early, SMS after engagement, voice for hot leads." | Each tab loads its own active prompt version | Multi-channel, Context |
| 1:10 | C1, Prospects, Dana Whitfield, Run now. Watch the timeline | "Research, qualification, planning and drafting run as separate agents." | Facts with sources, a score and a plan with reasons within about 10 seconds, then the draft and the send 20 seconds later | End to end, Context |
| 2:10 | Click Why on the draft, then a citation. Show the Gmail tab | "Every claim links to a source. The Guardian checks ten rules before anything sends." | Trace drawer: prompt version, retrieved chunks, cost, gate list | Context, Engineering |
| 2:40 | On Dana's page click Simulate reply and send "Sounds relevant, free next week?". Then on Rajiv's page send "Send your SOC 2 report and security questionnaire." | "Replies run through the same code as a real Gmail reply." | Dana: classified, two slots offered. Rajiv: a security-questionnaire escalation for Priya, with a suggested reply | End to end |
| 3:40 | The DronaHQ agent-builder tab | "The agent runs on DronaHQ and calls our API through MCP. Prompt versions come from our database." | Instructions with variables, our MCP server in the tools, the same run in our log | DronaHQ |
| 4:10 | Settings, Demo tools, Advance 24 hours three times. Open Tomas. Pause LinkedIn on C1 | "No reply in three days, so the Sequencer switches channel and angle. Pause LinkedIn and it replans." | Tomas gets a LinkedIn step (`SANDBOX`). The feed reads "Replanned 8 prospects: LinkedIn paused, day-3 touch moved to email" | Multi-channel, Innovation |
| 4:50 | C3, Noor Haddad, approve the call | "Voice needs approval in this campaign." | Approval, then the call records (real on DronaHQ Voice when connected, otherwise Play scripted call outcome and say so) | Multi-channel, DronaHQ |
| 5:20 | C2 dashboard, Pause. Agent Activity, then Command Center. Open C4 (Draft) and click Try a send | "Pause writes one row. Only C2 stops." | C2 turns amber and its counters freeze. C1 and C3 keep adding rows. The C4 send returns `campaign_not_live` | Product, Engineering |
| 6:10 | Approvals, Conflicts tab: Sam Okafor. Then Stop all, wait for the banner, Resume platform | "Sam sits in two campaigns. The engine gave him to C1 on ICP score, and I can override it. The kill switch stops everything." | Conflict row names the rule. A red banner spans every screen | Engineering, Product |
| 6:40 | Analytics, then Prompts, Compare v1 and v2 | "Cost per qualified lead by campaign, and prompt versions scored against a golden set." | Table renders. Golden scores are measured, not typed in | Measurement |

## The five-minute cut

Drop the voice row, the Analytics row, the conflict half of the 6:10 row (keep the kill switch), the LinkedIn pause in the 4:10 row, and Rajiv's reply. The pause proof, the DronaHQ detour, the grounded draft and the live email always stay.

## Preflight, 30 minutes before

- [ ] `make reset` finished, `/health` is green.
- [ ] Demo clock offset is 0, the kill switch is off, C1, C2 and C3 are Live, C4 is Draft.
- [ ] Warm-up: run one throwaway prospect through research and draft, then reset again.
- [ ] Open the public link in a private window and sign in with a chip.
- [ ] The Gmail seed inbox is open, the team phone is charged, and a test call worked.
- [ ] Tabs are open in order and the backup video is paused on its first frame.
- [ ] A phone hotspot is ready.
- [ ] Browser zoom matches 1366 by 768.

## If a step fails

Say what happened in one sentence and move on.

| Step | Failure | Recovery |
| --- | --- | --- |
| Run now | Research is slow | Open the prospect from the warm-up. If three warm-ups were slow, set `AGENT_PROVIDER_RESEARCHER=direct` before the demo |
| Email | Nothing arrives in 20 seconds | Show the send event with its message id, then the warm-up email |
| Reply | The simulator errors | Reload once, then open the seeded reply in Conversations |
| DronaHQ detour | The builder asks for a login | Show `dronahq/screenshots/` |
| Voice | The real call fails | Demo tools, Play a scripted call outcome, and say "scripted outcome" |
| Pause | The freeze looks unclear | Filter Agent Activity by campaign, or show the green `test_pause_isolation` run |
| Any | The app is unreachable | Switch to the backup video, then show the repo and the README |

## Judge card

1. Sign in with a demo chip and create a campaign from the C1 template. Try Activate and read the checklist.
2. Open Prompts on C3, edit the tone, save v3, and compare it with v2.
3. Pause a campaign and watch Agent Activity.

Reset between judging sessions with `make reset` (or Settings, Demo tools, Reset data as admin).
