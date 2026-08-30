# Branch currency

Consume only the exact `branch_currency` object emitted by the current
snapshot.  No object means no branch update, whatever else changed remotely.

## `BEHIND`

`BEHIND` is a human blocker in this target-only capability. Preserve the exact
item, including `route`, `expected_head_sha`, base identity, and host
capability, in the checkpoint evidence. Do not invoke a branch-update
operation or infer one from prose. An unknown or denied capability is also a
human blocker.

## `DIRTY` and `CONFLICTING`

These states are read-only human blockers. Preserve the exact conflict
evidence, current head, and capability fields and stop; do not alter the target
while the choice is unresolved.

The semantic fingerprint is the sorted conflicted paths and their staged blob
identities.  It is independent of later base movement, so repeated evidence
can be recognized without replaying an action.

## Defect evidence

If a new head is an unexpected two-parent update, record
`unrequested_base_merge` from the snapshot as a defect residual.  Keep
watching the named pull request, but do not undo the update.
