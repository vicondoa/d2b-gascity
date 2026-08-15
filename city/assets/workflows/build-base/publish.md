This city uses the resolved Pack v2 `build-base` publication step as its only
publication seam. Do not copy or replace an upstream formula body.

gc.publication.worker_marker=d2b-gascity-publication-worker-v1
gc.publication.push={{push}}
gc.publication.open_pr={{open_pr}}

The rendered marker and the two rendered boolean inputs are an exact machine
contract for the packaged `d2b-gascity-publication-worker`. The worker is a
trusted deterministic subprocess, not an ACP or model-backed agent. It claims
one routed bead through the official `gc gc claim` protocol, rejects any
publisher task without this marker, and closes only the claimed step.

When both inputs are false, the worker records the upstream no-op publish
metadata on the workflow root and this step, writes a safe artifact when
`GC_ARTIFACT_DIR` is available, and closes the step successfully. When PR
publication is enabled, it resolves `gc.input_convoy_id` from the workflow
root. A synthetic drain-unit convoy is replaced with its
`gc.drain_member_id`; the synthetic bead never receives source metadata.

After the publish step is claimed, the worker verifies the source worktree is
clean, computes its current `HEAD`, and sets and reads back
`gc.publication.expected_head_sha` on the source anchor. It then invokes
`d2b-gascity-publish-pr <source-anchor-id>` from that worktree. The helper's
safe URL, SHA, and branch record, together with the required
`gc.build.publish_*` metadata, are written to both the workflow root and this
step before close. Helper diagnostics are never copied into bead metadata,
artifacts, or worker output.

The helper owns the final Beads readback, exact `origin/v3` ancestry proof,
create-only `gascity/*` branch race handling, and pull-request reconciliation.
Do not call a merge, auto-merge, merge queue, force, or ruleset-bypass command.
