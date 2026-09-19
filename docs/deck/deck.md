# Deck outline

`python scripts/build_deck.py` writes `Cadence.pptx` (14 slides) and reads its numbers from the database, so the figures on the slides match the live workspace. Regenerate it after a `make reset` and after the final prompt freeze.

| # | Slide | Message |
| --- | --- | --- |
| 1 | Cadence | Launch a campaign, watch agents work it, pause it in one click |
| 2 | The problem | Research, copy and logging eat the day. Nobody can say why a message went out |
| 3 | One SDR, not seven bots | Five design rules, each with a visible artifact |
| 4 | Architecture | Agents never send. Every send passes the Guardian, then a channel adapter |
| 5 | The agents | Six model-backed units and one deterministic supervisor |
| 6 | DronaHQ is core | Apps Studio, hosted agents, voice, and our MCP tools. Real code underneath |
| 7 | The policy gate | Ten ordered checks, one reason code each, idempotent |
| 8 | Campaigns run side by side | Pause writes one row and leaves the others running |
| 9 | Grounded personalisation | Every claim traces to a source. A trace shows why |
| 10 | Measurement | Funnel, reply rate, cost per qualified lead and golden-set scores, read from the database |
| 11 | Reliability | 86 tests, failure injection, security checks |
| 12 | What works, honestly | Sandbox is an approved state and the badge tells the truth |
| 13 | Try it yourself | The judge card and the repository |

Live demo: `docs/demo.md`. Backup video: recorded at H49 from the final build.

Slide 7 was added after this outline: "The DronaHQ manager app", the native Apps Studio screens.
