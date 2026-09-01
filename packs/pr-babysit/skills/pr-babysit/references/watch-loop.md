# Checkpoint mechanics

Gas City supplies session and retry lifecycle.  This capability performs one
short checkpoint per native turn; it does not own a resident process.

## State and deduplication

The wake payload supplies a stable watch bead ID.  `pr-snapshot` keeps one
`state.json` and an advisory lock at exactly `$GC_DIR/state/<watch-id>`, after
validating every path component and rejecting symlinks.  The journal records
only safe identifiers, observed head SHA, current checks, feedback
dispositions, branch-currency evidence, invocation values, and human
residuals. Payloads remain in the emitted result and are not used as
executable input.

The action protocol is **claim -> act -> confirm**:

1. Claim the exact source identity and current head.
2. If the pull-request template is invalid, use
   `dispatch-template-remediation` and stop before review or CI.
3. After the template is valid, perform only the permitted source action
   through `dispatch-repair`; a checkpoint itself remains read-only.
4. Take a new snapshot and confirm the resulting remote state before marking
   the action complete.

A changed head, source identity, or invocation value invalidates the claim.
An unconfirmed action is never replayed blindly.

## Checkpoint cadence

The native order chooses when to invoke another checkpoint.  A checkpoint
returns immediately when no actionable source is present.  After a confirmed
action, the next checkpoint starts with a new snapshot so old-head CI cannot
be reused.

## Bounded readiness

The default quiet window is five minutes.  A current review signal blocks the
ordinary readiness report while work continues around already-posted
feedback.  At the bounded stale-review limit, report the uncertainty plainly;
never turn silence into approval.

Read `references/tick.md` for the ordered turn and
`references/settle.md` for the terminal gates.
