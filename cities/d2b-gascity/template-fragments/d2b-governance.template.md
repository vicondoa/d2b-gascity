{{ define "d2b-governance" -}}
## repository governance

Choose the publication target from the rig that owns the work.

For the `d2b` product rig, keep work targeted to `v3`. Every work bead handed
to publication must carry `metadata.target=v3` and
`metadata.merge_strategy=pr`.

Use the official Gas City pack workflows (`build-basic`, `implement`,
`github-issue-fix`, and `publish`) and the Discord `mol-d2b-discord-fix-issue`
extension. The extension is product-only because its workspace setup targets
`origin/v3`; never use it for city-source work.

For the `city-source` rig, keep `d2b-gascity` source work targeted to `main`.
Every work bead handed to publication must carry `metadata.target=main` and
`metadata.merge_strategy=pr`. Never apply the d2b `v3` target to city-source
work. Use the stock official workflows without the Discord extension.

Both rigs default to `open_pr=true`, `push=true`, and `drain_policy=separate`
so implementation uses worktrees and publication opens a pull request.
Publication must refuse direct merges and accept only the pull-request
handoff. The handoff receipt's
`target=<rig>/pr-babysit.pr-babysitter` is distinct from the watch's
`base_ref=v3` or `base_ref=main` and the publication bead's
`merge_strategy=pr`. The rig-imported `pr-babysit` agent
`pr-babysit.pr-babysitter` and `mol-pr-babysit-repair` Formula v2 are
target-only: they may inspect and repair the named pull request on its
existing head branch, but may not create a replacement pull request. Repairs
are same-repository-only; fork or cross-repository PRs are human blockers in
v1. Before repair, the operator must provide an absolute, non-symlink,
executable `PR_BABYSIT_VALIDATOR` and set
`PR_BABYSIT_VALIDATOR_ATTESTED=credential-isolated-v1`; it runs `make check`
in a credential- and network-isolated environment, and a missing validator
blocks repair. It may never merge; it may never force-push or rebase, approve
workflow runs, or update branch currency. Merge decisions remain human-owned.
Host branch protection for `v3` is defense-in-depth: it must require pull
requests and apply to administrators. This repository does not claim that the
current host is already configured that way.
{{- end }}
