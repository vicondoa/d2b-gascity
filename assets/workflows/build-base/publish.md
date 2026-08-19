This is the `build-base` publish stage. Treat it as a virtual contract that
concrete formulas may override.

Before any publication action, read `gc.publication.base_ref` from the
workflow source-anchor metadata. Also read `gc.publication.base_sha` and the
absolute `work_dir`. Require all of the following before publication:

- `gc.publication.base_ref` is `origin/v3`
- `gc.publication.base_sha` is a lowercase 40-character commit SHA
- the clean worktree `HEAD` descends from that recorded base SHA
- `refs/heads/v3` on `origin` still equals the recorded base SHA
- the remote repository is exactly `vicondoa/d2b`
- the GitHub pull request base is `v3`

If the metadata, worktree, remote, branch, base SHA, PR base, or authorization
does not match, fail closed before changing the remote or creating a pull
request. A moved `origin/v3` requires a fresh worktree preparation; never
silently publish from a stale base.

If `push` is enabled, push the finalized build result using the official
create-if-absent or expected-object-id update contract. Push only when
authorized; never force-push or update the base branch.

If `open_pr` is enabled, create a pull request only after an authorized push
succeeds, and set its base explicitly to `v3`. Do not create a pull request
when `open_pr` is disabled. Never merge a pull request or bypass repository
rules.

If publishing is disabled, record the exact reason and leave the artifacts
ready for a later publisher.

Write a publish result artifact under the workflow artifact root when one is
available. Record the same publish outcome on the workflow root bead and this
publish step before closing.

Required workflow root metadata:

- `gc.build.publish_status=published|noop|failed`
- `gc.build.publish_action=push|pr|push_pr|noop|failed`
- `gc.build.publish_recorded_at=<UTC timestamp>`
- `gc.build.publish_artifact_path=<publish result artifact path>`
- `gc.build.publish_reason=<short machine-readable reason>`

For disabled publishing, use `gc.build.publish_status=noop`,
`gc.build.publish_action=noop`, and a reason such as
`push=false_open_pr=false`. Also record whether remotes were present with
`gc.build.publish_remote_status`.

Close this step only after the publish action or explicit no-op is recorded on
both the workflow root and the publish step.
