---
description: Lint, test, update BUILD_STATUS.md, and commit the current slice
---

Run a checkpoint for: $ARGUMENTS

1. Run `make lint` and `make test`. Fix every failure. Paste the final summary lines.
2. Run the feature against the local stack and confirm it works end to end.
3. Update `BUILD_STATUS.md`: phase status, requirement tracker rows with proof ids, blockers, next steps, and the decisions log.
4. Update `MANUAL_ACTIONS.md` if you found a new manual step.
5. Commit with `type(scope): reason`. Print the commit hash and the next three steps.
