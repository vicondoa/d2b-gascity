# d2b-gascity

`d2b-gascity` is the source repository for one portable Gas City city and
one `vicondoa/d2b` rig on branch `v3`. It is city configuration, not a second
d2b product repository.

## Repository boundary

This repository owns the root Pack v2 city, the d2b rig declaration, and the
official core, Beads, Gas City pack, and Discord imports. The Gas City pack
supplies planning and implementation formulas, the `gc.mayor` coordinator
skill, and rig roles such as `run-operator`, `implementation-worker`,
`publisher`, and `requirements-planner`. Discord supplies native
interactions, administration, gateway, chat bindings, launchers, and
workflow helpers. The imported packs are source-only; native Gas City owns
their lifecycle and state.
The local `mol-d2b-discord-fix-issue.toml` extends the official Discord
workflow only to start first-run d2b work from `origin/v3` and safely resume
recorded branches with fail-closed checks. Publication stays on `v3` with
human-owned merge decisions.

The host supplies `gc`, `copilot`, optional `codex`, `gh`, and optional
ingress tooling. The city defaults to Copilot CLI and keeps stock Codex
available.
Runtime installation and host integration belong to the separate private
`vicondoa/gascity.nix` repository or another compatible source. This
repository contains no Nix packaging or host configuration.

## Layout

```text
.
|-- city.toml
|-- pack.toml
|-- packs.lock
|-- agents/
|   `-- mayor/
|-- formulas/
|   `-- mol-d2b-discord-fix-issue.toml
|-- template-fragments/
|   `-- d2b-governance.template.md
|-- docs/
|   |-- operations.md
|   |-- testing.md
|   |-- designs/
|   `-- plans/
`-- tests/test_city.py
```

Native Gas City state, rig paths, Beads and Dolt data, worktrees,
credentials, logs, and other machine-local values stay outside tracked
files.

## Native workflow

Follow [docs/operations.md](docs/operations.md) for initialization, Gas City
pack roles and formulas, native lifecycle commands, Copilot CLI default
lanes, the alternate Codex provider, and the complete official Discord setup
and operating model. The provider design is
[docs/designs/2026-08-27-001-copilot-cli-provider.md](docs/designs/2026-08-27-001-copilot-cli-provider.md).
[docs/testing.md](docs/testing.md) describes the focused checks and the
manual live smokes.

Publication must persist `metadata.target=v3` and `metadata.merge_strategy=pr`
and refuse direct merges. Never merge or force-push. Host branch protection
for `v3` is defense-in-depth and must require pull requests and apply to
administrators; this repository does not claim the current host is already
configured that way.

## Governance and privacy

Keep one logical change per commit and human ownership of merges. Use ASCII
hyphens. Never commit private authorities, addresses, users, channels, roles,
credential values or paths, runtime state, live prompts or responses, or
private pull-request payloads. Keep Copilot Requests, Discord app
credentials, and d2b publication credentials separate. Generic placeholders
and `127.0.0.1` are allowed. Review the staged file list and complete diff
before committing.

## License and provenance

Local content is Apache-2.0. Imported upstream sources retain their licenses
and notices. See [LICENSE](LICENSE) and [PROVENANCE.md](PROVENANCE.md).
