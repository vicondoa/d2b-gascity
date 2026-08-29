If open_pr is {{open_pr}}, create a PR only after push succeeds and
sanitized title/body from final report {{final_report}} pass policy.

This file shadows `gascity/formulas/publish.formula.toml` only at its
`open-pr` description asset.

This city adds a target-only babysitting handoff after the official PR
creation behavior above. The publication remains pull-request-only. Never merge.
Never force-push. Never rebase, approve a workflow, or create a replacement
pull request.

When `open_pr` is true:

1. Create or update the pull request through the official publication path.
2. Read its canonical URL and number from GitHub, not from prose in the final
   report.
3. Run the rig-imported command with the current publication bead:

   ```sh
   gc pr-babysit pr-babysit publication-handoff \
     --rig "$GC_RIG" \
     --publication-bead-id "{{issue}}" \
     --url "$PR_URL" \
     --pr-number "$PR_NUMBER"
   ```

4. Immediately before closing this publication step, verify the machine-owned
   receipt:

   ```sh
   gc pr-babysit pr-babysit verify-handoff \
     --rig "$GC_RIG" \
     --publication-bead-id "{{issue}}" \
     --url "$PR_URL" \
     --pr-number "$PR_NUMBER"
   ```

Both commands must exit successfully and return JSON with
`"verified":true`, the same stable watch ID, and the binding-qualified target
for the owning rig. If either command fails, do not close publication. Report
the handoff blocker without attempting a merge or another pull request.
