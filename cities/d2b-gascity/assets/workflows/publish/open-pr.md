If open_pr is {{open_pr}}, create a PR only after push succeeds and
sanitized title/body from final report {{final_report}} pass policy.

This file shadows `gascity/formulas/publish.formula.toml` only at its
`open-pr` description asset.

This city adds a target-only babysitting handoff after the official PR
creation behavior above. The publication remains pull-request-only. Never merge.
Never force-push. Never rebase, approve a workflow, or create a replacement
pull request.

When `open_pr` is true:

1. Read `.github/PULL_REQUEST_TEMPLATE.md` from the repository and create or
   update the pull request through the official publication path using that
   structure. Preserve `Summary`, `Validation evidence`, and `Notes`; check
   every required item only from truthful evidence. The repository gate item
   requires an exact successful `make check` run. If that evidence is absent,
   route back to implementation instead of checking the item.
2. Read its canonical URL and number from GitHub, not from prose in the final
   report.
3. Run the city-scoped command with the current publication bead:

   ```sh
   gc core-city pr-babysit publication-handoff \
     --rig "$GC_RIG" \
     --publication-bead-id "{{issue}}" \
     --url "$PR_URL" \
     --pr-number "$PR_NUMBER"
   ```

   The command first routes the watch without waking it, persists matching
   `handoff_verified=true` identity receipts on the publication and watch
   beads, then nudges the binding-qualified babysitter. A complete receipt
   requires `handoff_route_status=complete` and
   `handoff_wake_status=delivered`. A route or wake failure records a
   recoverable `handoff_route_status=route-failed` state without leaving a
   verified receipt; `handoff_wake_status=ready` is only a recoverable
   wake-replay intermediate. Repeating a complete receipt does not issue
   another wake.

4. Immediately before closing this publication step, verify the machine-owned
   receipt:

   ```sh
   gc core-city pr-babysit verify-handoff \
     --rig "$GC_RIG" \
     --publication-bead-id "{{issue}}" \
     --url "$PR_URL" \
     --pr-number "$PR_NUMBER"
   ```

Both commands must exit successfully and return JSON with
`"verified":true`, the same stable watch ID, and the binding-qualified target
for the owning rig. If either command fails, do not close publication. Report
the handoff blocker without attempting a merge or another pull request.

The publication bead must already persist `merge_strategy=pr` and its
repository target as `base_ref`, `target`, or `target_branch`; the handoff
never infers a missing target.
