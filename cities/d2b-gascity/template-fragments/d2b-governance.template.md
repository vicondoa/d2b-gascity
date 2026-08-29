{{ define "d2b-governance" -}}
## d2b governance

Keep d2b work targeted to `v3`. Every d2b work bead handed to publication
must carry:

- `metadata.target=v3`
- `metadata.merge_strategy=pr`

Use the official Gas City pack workflows (`build-basic`, `implement`,
`github-issue-fix`, and `publish`) and the Discord `mol-d2b-discord-fix-issue`
extension. d2b formula defaults are `open_pr=true`, `push=true`, and
`drain_policy=separate` so implementation uses worktrees and publication
opens a pull request. Publication must refuse direct merges and accept only
the pull-request handoff. Never merge or force-push; merge decisions remain
human-owned. Host branch protection for `v3` is defense-in-depth: it must
require pull requests and apply to administrators. This repository does not
claim that the current host is already configured that way.
{{- end }}
