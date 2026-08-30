# Report

Start every terminal report with one status line:

- `Looks merge-ready - <evidence>. Your call for final integration.`
- `Cautiously looks ready - <review evidence>. Your call for final integration.`
- `Merged`, `Closed`, `Blocked`, `Budget exhausted`, or `Paused` for the other
  terminal states.

Then summarize the target pull request, the feedback themes handled, current
head CI results, pushes actually observed, elapsed budget, and every parked
blocker.  Distinguish actions performed from actions merely planned.  Never
claim that a green snapshot guarantees future readiness.

When a human decision is required, put the complete residual immediately after
the status line under `## Needs your decision`.  Preserve the quoted source
and its exact evidence; do not close the feedback that remains unresolved.
