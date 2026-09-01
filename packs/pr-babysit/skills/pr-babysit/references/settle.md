# Stop conditions and settle

## `merge-ready`

Report `merge-ready` only when all of these facts come from a current
snapshot and are supplied to the checkpoint as one structured
`merge_ready_evidence` object:

- the pull request is open and the head SHA is current;
- the current result is certain and `merge_state_status` is `CLEAN`;
- every observed check is terminal and successful;
- there are no actionable threads or feedback candidates;
- there are no unresolved human decisions;
- `branch_currency` and `branch_currency_blocker` are clear;
- the pull-request template is valid with truthful `make check` evidence;
- the quiet window has elapsed and no review is still expected.

The object must contain `current_head_sha`,
`mergeability_certain`, `branch_clean`, `required_checks_terminal`,
`required_checks_successful`, `no_actionable_feedback`,
`no_pending_human_interaction`, `no_currency_item`,
`template_followed`, and
`quiet_window_satisfied`. The SHA must match the current snapshot and every
boolean must be `true`; missing or false evidence is rejected.

This is an honest handoff, not permission for the human's final integration
decision.  A later review or check can change the result.

The current checkpoint must still be within the `active_since` eight-hour
active budget and before the three-day RFC3339 backstop.  If either budget
expires while the watch is `watching` or `waiting`, persist `exhausted`
instead of reporting `merge-ready`.

## Other stops

- `MERGED` or `CLOSED` is terminal.
- A missing repository, branch, authority, or current-base proof is blocked.
- An exhausted repair or time budget is exhausted.
- A human decision remains a standing blocker until its exact evidence changes
  or the caller records an answer.
- `BEHIND`, dirty, conflicting, or unknown branch-currency evidence is a human
  blocker; do not update the branch from a checkpoint.

An in-progress review signal delays the readiness report but never delays
handling feedback already posted.  If a signal disappears without a completion
signal, retain the incomplete lifecycle and use a bounded cautious-ready
decision rather than waiting forever.
