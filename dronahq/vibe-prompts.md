# Vibe Coding prompts

One screen per archetype, then the team clones each archetype for the remaining screens. Paste each prompt into Apps Studio Vibe Coding after the REST connector `cadence_api` exists. Record any edit made after generation below the prompt.

## List with filters (Campaign List)

```text
Build a screen called Campaign List. Use the REST connector cadence_api and call GET /campaigns with the query parameter status from a segmented control (All, Live, Paused, Draft). Show a table with the columns name, ICP summary, status, prospects, outreach, replies, meetings, owner and last activity. Show status as a pill: Live green with a dot, Paused amber, Draft grey outline. Tint Paused rows amber and mute Draft rows. Add a Pause or Resume button per row that calls POST /campaigns/{id}/pause or /resume, then reloads the table. Show an empty state and an error row with Retry. Keep a clean, neutral B2B look with one accent.
```

## Detail with tiles (Campaign Dashboard)

```text
Build a screen called Campaign Dashboard for one campaign id. Call GET /campaigns/{id}/dashboard. At the top show the campaign name, a status pill and a large Pause or Resume button. Below show tiles for prospects, contacted, replies, meetings and jobs held, then a funnel with seven stages and stage conversion, then a card with agent counters and one switch per agent that calls PUT /campaigns/{id}/agents/{agent}. When the status is paused, show an amber banner that reads Paused by {name} at {time}. Reload every 3 seconds.
```

## Feed (Command Center)

```text
Build a screen called Command Center. Show tiles for live campaigns, prospects in flight, touches today, replies today, meetings this week and items that need me. Below them show a strip of campaign cards with a funnel mini bar and a Pause or Resume button. Show a live feed of the last 20 events from GET /activity?since_id={{last_id}} with a colour tag per campaign, and highlight new rows for two seconds. Show a red Stop all button in the top bar that calls POST /kill-switch after a confirmation dialog.
```

## Form (Create Campaign)

```text
Build a screen called Create Campaign with collapsible sections for Identity, Targeting, Agents, Channels and limits, Prompts, Knowledge and Reps. Add a template picker. Show a sticky checklist on the right with six items and disable the Activate button until every item passes. Buttons: Save draft (POST /campaigns), Run dry run (POST /campaigns/{id}/dry-run) and Activate (POST /campaigns/{id}/activate). Show the failing checks when activation returns 409.
```

## Edit log

| Date | Screen | Change after generation |
| --- | --- | --- |
| | | |
