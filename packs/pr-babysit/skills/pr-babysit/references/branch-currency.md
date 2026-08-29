# Branch currency

Consume only the exact `branch_currency` object emitted by the current
snapshot.  No object means no branch update, whatever else changed remotely.

## `BEHIND`

Proceed only when the item says `route: normal-base` and
`host_branch_update_capability: true`.  Claim the item before writing, then
re-read the pull request and compare its current head and base with the
recorded observations.  Send the recorded `expected_head_sha` to the host
branch-update endpoint exactly once.  A head mismatch is stale evidence:
take a new snapshot and do not resubmit.

Host acceptance is not completion.  Confirm the action only after a fresh
snapshot proves the expected base is present and the currency item is clear.
An unknown or denied capability is a human blocker, never a reason to guess.

## `DIRTY` and `CONFLICTING`

These states require a clean, exact-head checkout and positive intent evidence
before any local repair.  A missing checkout, stale SHA, ambiguous resolution,
or absent write authority is a blocker.  Preserve the conflict evidence and
stop; do not alter the branch while the choice is unresolved.

The semantic fingerprint is the sorted conflicted paths and their staged blob
identities.  It is independent of later base movement, so repeated evidence
can be recognized without replaying an action.

## Defect evidence

If a new head is an unexpected two-parent update, record
`unrequested_base_merge` from the snapshot as a defect residual.  Keep
watching the named pull request, but do not undo the update.
