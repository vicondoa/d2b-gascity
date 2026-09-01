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
Those generic workflows start new branch work from the repository target. They
must not be used to add operator-requested source changes to an already watched
pull request. Bind that work bead through
`gc core-city pr-babysit dispatch-requested-repair` so the existing PR head,
single action claim, configured reviewer, and one-push fence remain
authoritative.

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
v1. The implementation worker owns the sole repository-default `make check`,
records the exact worker signoff SHA, and commits only after it passes. The
reviewer binds its verdict to that candidate. Run-operator verifies those
records and the unchanged remote head before one normal push; it does not
rerun `make check`. It may never merge; it may never force-push or rebase,
approve workflow runs, or update branch currency. Merge decisions remain
human-owned.
The deterministic state CLI is exposed only through the city-scoped
`core-city` pack as `gc core-city pr-babysit <action>`, delegating to the
rig-imported helper without importing that pack city-wide or exposing a second
command entrypoint.
Every PR must follow the canonical template and include truthful successful
`make check` evidence. The babysitter validates the body before review or CI;
invalid bodies are reduced to safe error codes and slung to the owning
publisher through one blocking remediation bead.
Host branch protection for `v3` is defense-in-depth: it must require pull
requests and apply to administrators. This repository does not claim that the
current host is already configured that way.
{{- end }}
