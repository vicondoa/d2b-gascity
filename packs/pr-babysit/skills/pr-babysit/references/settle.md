# Stop conditions and settle

## `merge-ready`

Report `merge-ready` only when all of these facts come from a current
snapshot:

- the pull request is open and the head SHA is current;
- the current result is certain and `merge_state_status` is `CLEAN`;
- every observed check is terminal and successful;
- there are no actionable threads or feedback candidates;
- there are no unresolved human decisions;
- `branch_currency` and `branch_currency_blocker` are clear;
- the quiet window has elapsed and no review is still expected.

This is an honest handoff, not permission for the human's final integration
decision.  A later review or check can change the result.

## Other stops

- `MERGED` or `CLOSED` is terminal.
- A missing repository, branch, authority, or current-base proof is blocked.
- An exhausted repair or time budget is exhausted.
- A human decision remains a standing blocker until its exact evidence changes
  or the caller records an answer.

An in-progress review signal delays the readiness report but never delays
handling feedback already posted.  If a signal disappears without a completion
signal, retain the incomplete lifecycle and use a bounded cautious-ready
decision rather than waiting forever.
