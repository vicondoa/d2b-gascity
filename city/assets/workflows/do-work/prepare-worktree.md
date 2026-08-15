<!--
  Narrow d2b override for the upstream gascity asset
  gascity/assets/workflows/do-work/prepare-worktree.md at
  f6741d94861aa14f0253deffbe9efb1cb3a35d92.
  Only the base ref is changed: d2b work starts at origin/v3.
-->

Resolve and publish the isolated worktree for this item. This is infrastructure
setup only. Do not edit source files in the launcher checkout.

1. Read the current step bead metadata and resolve `gc.root_bead_id`.
2. Resolve and validate the source anchor from the do-work root metadata:
   `gc.input_convoy_id` must match `{{convoy_id}}`; for a drain-unit convoy,
   use its `gc.drain_member_id` and never persist state on the synthetic bead.
3. Validate `{{context_path}}`, file ownership, and verification policy for the
   source anchor.
4. Create or reuse `$(pwd)/worktrees/<source-anchor-id>`. If it is missing:

   ```bash
   git fetch --prune origin v3
   git worktree add "$WORKTREE" --detach origin/v3
   ```

   If it exists but is not a worktree for this repository, fail closed.
5. Persist the absolute worktree path on the source anchor with
   `gc bd update <source-anchor-id> --set-metadata work_dir=<absolute path>`.
   Verify `work_dir` before closing with `gc.outcome=pass`.
