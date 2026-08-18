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
5. Refresh and verify the fresh `origin/v3` tip:

   ```bash
   git -C "$WORKTREE" fetch --prune origin v3
   BASE_SHA="$(git -C "$WORKTREE" ls-remote origin refs/heads/v3 \
     | awk 'NF == 2 && $2 == "refs/heads/v3" { print $1 }')"
   test "$(printf '%s' "$BASE_SHA" | grep -Ec '^[0-9a-f]{40}$')" = 1
   test "$(git -C "$WORKTREE" rev-parse --verify \
     refs/remotes/origin/v3^{commit})" = "$BASE_SHA"
   ```

6. Persist and read back the production source anchor contract in one update:

   ```bash
   gc bd update "$SOURCE_ANCHOR_ID" \
     --set-metadata "work_dir=$WORKTREE" \
     --set-metadata "gc.publication.base_ref=origin/v3" \
     --set-metadata "gc.publication.base_sha=$BASE_SHA"
   gc bd show "$SOURCE_ANCHOR_ID" --json --long
   ```

   Verify the readback contains the absolute `work_dir`,
   `gc.publication.base_ref=origin/v3`, and the exact fresh
   `gc.publication.base_sha` before closing with `gc.outcome=pass`.
