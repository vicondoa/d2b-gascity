Resolve and publish the isolated worktree for this item. This is infrastructure
setup only. Do not edit source files in the launcher checkout.

1. Read current step bead metadata and get `gc.root_bead_id`; hard-fail if it is
   missing. Read that do-work root with `gc bd show <root-bead-id> --json`. If
   `gc bd show --json` returns a one-element list, unwrap the first element before
   reading metadata.
2. Resolve `<source-anchor-id>` from the do-work root:
   - read root metadata `gc.input_convoy_id`; hard-fail if it is missing
   - verify `gc.input_convoy_id` matches rendered runtime convoy `{{convoy_id}}`
   - read that input convoy with `gc bd show <input-convoy-id> --json`; unwrap a
     one-element list response before reading metadata
   - if input convoy metadata has `gc.synthetic_kind=drain-unit-convoy`, use
     input convoy metadata `gc.drain_member_id`
   - do not use the synthetic drain-unit convoy id as `<source-anchor-id>`;
     hard-fail if the selected source anchor id equals the synthetic input convoy id
   - otherwise use `<input-convoy-id>` as the source anchor
   - if root metadata also has `gc.drain_member_id`, it must match the selected
     drain member
3. Validate context path {{context_path}}, files ownership, and verification
   policy for the resolved source anchor.
4. Create or reuse a deterministic git worktree at
   `$(pwd)/worktrees/<source-anchor-id>`, based on the current `origin/v3` tip.
   Never use the launcher's local `HEAD`.
   - Fetch the required branch: `git fetch --prune origin v3`.
   - If the path is missing, create it detached:
     `git worktree add "$WORKTREE" --detach origin/v3`.
   - If the path exists but is not a worktree for this repository, fail closed.
   - If the existing worktree is dirty, fail closed instead of discarding work.
5. Resolve the authoritative base SHA:
   - Read `refs/heads/v3` with `git -C "$WORKTREE" ls-remote origin`.
   - Require exactly one lowercase 40-character commit SHA.
   - Require `refs/remotes/origin/v3^{commit}` to resolve to the same SHA.
   - Check out that SHA detached in a clean reused worktree.
   - Require the worktree `HEAD` to equal that SHA before continuing.
6. Persist the source anchor contract in one update:
   - `work_dir=<absolute worktree path>`
   - `gc.publication.base_ref=origin/v3`
   - `gc.publication.base_sha=<authoritative base SHA>`

For synthetic drain-unit convoys, never persist this state on the synthetic
convoy. The original drain member or source anchor is authoritative. Read the
source anchor back and verify all three values before closing this step with
`gc.outcome=pass`.
