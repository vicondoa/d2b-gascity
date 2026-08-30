# Setup

## Preconditions

The babysitter receives one stable watch bead ID in its native wake payload.
The projection gate is mandatory and the first operation after it is:

```text
gc pr-babysit pr-babysit show --watch-id <watch-id> --json
```

The show result must be a watch record with verified `rig`, `github_host`,
`owner`, `repository`, `head_repository`, `pr_number`, `url`, `base_ref`,
`head_ref`, `head_sha`, and `generation` fields. It must also carry a complete
publication receipt: `handoff_verified=true`,
`handoff_watch_id=<watch-id>`,
`handoff_target=<rig>/pr-babysit.pr-babysitter`, and a publication bead
identity. Explicit `pending` or `route-failed` receipt states are blockers.
`head_repository` must equal `owner/repository`. A missing, malformed, stale,
or mismatched field is a blocker. Never resolve a target from a current branch
or from message text.

The helper speaks GitHub through `gh` and keeps its journal only at
`$GC_DIR/state/<watch-id>`. The path must be absolute, private to the watch,
and free of symlinks in every existing component. The helper rejects paths
outside that exact directory and creates only its lock and JSON journal there.

The watch checkpoint is read-only. It does not switch refs, edit files, create
a worktree, or push. Only the canonical `dispatch-repair` command may create
an action-scoped worktree for a permitted repair.
