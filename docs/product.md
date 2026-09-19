# Product one-pager

**Cadence** is an autonomous multi-channel SDR with a manager control plane. A Head of Sales or SDR manager launches a campaign, watches agents work it, and pauses it in one click.

| Item | Definition |
| --- | --- |
| Core user | Head of Sales or SDR manager running three to five outbound programs with one to three human reps |
| Secondary user | A human rep who receives escalations and booked meetings |
| Core problem | Reps spend most of their day on research, copy and logging. Quality varies by rep and by day, and nobody can answer why a message went out |
| Main workflow | The manager defines a campaign, agents run the loop per prospect, the manager approves edge cases and reads results |

## Screens

Command Center, Campaigns, Campaign Dashboard (Overview, Prospects, Agent Activity, Prompts, Knowledge, Config), Create Campaign with a pre-launch checklist and dry run, Prospect Explorer and Detail with a decision trace, Conversations, Approvals (approvals, escalations, conflicts), Agent Activity, Prompts and Harness, Knowledge Base, Analytics, Settings (integrations, reps, suppression list, demo tools), and the global kill switch in the top bar.

## Design principles

- State at a glance: Live is green with a dot, Paused is amber with an icon and a banner, Draft is a grey outline, and an active kill switch paints a red bar across every screen. Colour never carries meaning alone.
- Two clicks to "why": any message, score or decision opens a trace drawer.
- Pause is instant and safe, with an undo toast. The kill switch takes a confirm.
- One typeface family (Onest), an ink-black primary button, cream page bands, white cards and a 16-pixel radius: the BizLink language from the prototype in `frontend/prototype/`.
- Honest labels: every message shows LIVE, SANDBOX or REPLAY, and demo data carries a DEMO chip.
