# Apps Studio app spec

App name `Cadence`. Public Access on. One REST connector `cadence_api` with base URL `${BASE_URL}` and header `Authorization: Bearer {{jwt}}`.

The full control plane also ships as a static page at `${BASE_URL}/`. In Apps Studio it is embedded in a web component on the `Workspace` screen, and the native screens below cover the archetypes the judges asked about. Each native screen polls the same endpoints as the static page.

| Screen | Archetype | Endpoint bindings | Refresh |
| --- | --- | --- | --- |
| Login | Form | `POST /auth/login`, store `token` in the app variable `jwt` | none |
| Command Center | Dashboard with tiles and feed | `GET /campaigns`, `GET /activity?since_id={{last_id}}`, `GET /approvals` | timer, 3 s |
| Campaign List | List with filters | `GET /campaigns?status={{status}}`, row action `POST /campaigns/{id}/pause` and `/resume` | on action, then timer |
| Campaign Dashboard | Detail with tiles | `GET /campaigns/{id}/dashboard`, `PUT /campaigns/{id}/agents/{agent}`, `PUT /campaigns/{id}/channels/{channel}` | timer, 3 s |
| Approvals Inbox | List and detail | `GET /approvals`, `POST /approvals/{id}/decide`, `GET /escalations`, `GET /conflicts`, `POST /conflicts/{id}/resolve` | timer, 5 s |
| Agent Activity | Feed | `GET /agent-runs?campaign_id={{campaign}}`, `POST /agent-runs/{id}/retry` | timer, 3 s |
| Prompt and Harness | Editor | `GET /campaigns/{id}/prompts`, `POST /campaigns/{id}/prompts`, `POST /prompts/{version_id}/activate` | on action |
| Kill switch | Top bar control | `GET /kill-switch`, `POST /kill-switch` | timer, 3 s |

If a native screen cannot poll on a timer, it gets a Refresh button and a reload on screen focus, and the embedded static page carries the live feed.
