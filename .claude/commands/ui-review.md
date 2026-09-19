---
description: Compare the live app with the prototype at 1366x768 and fix visual deviations
---

Review the UI for: $ARGUMENTS (default: every route)

1. Start the app with `make dev`. Use the Playwright MCP tools to open two pages at 1366 by 768: the prototype at `frontend/prototype/cadence-prototype.html` (file URL) and the live app. Log in as the manager demo user in both.
2. For each route, capture the prototype and the live app side by side. Capture loading, empty, and error states where the live app has them.
3. Compare typography, spacing, hierarchy, table density, component shapes, and color use against the prototype and `docs/design-system.md`. Ignore data differences (names, counts, timestamps). Layout and style must match.
4. List deviations ranked by visual impact. Flag any off-token value, gradient other than the skeleton shimmer, and inline style that bypasses tokens.
5. Fix the top deviations in `frontend/css/tokens.css` and the component styles. Capture again and confirm.
6. Save final captures to `docs/screenshots/` and record the result in `BUILD_STATUS.md`.
