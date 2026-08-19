# d2b-gascity

`d2b-gascity` is the source repository for one portable Gas City city and
one `vicondoa/d2b` rig on branch `v3`. It is city configuration, not a second
d2b product repository.

## Repository boundary

This repository owns the root Pack v2 city, the d2b rig declaration, the
official Compound Engineering and Discord imports, the two narrow `v3`
workflow overrides, and focused portable-city checks. It contains no Nix
distribution or host deployment module. Install `gc` and any optional
integration or proxy binaries through the separate private
`vicondoa/gascity.nix` repository or another compatible source.

## Layout

```text
.
|-- city.toml
|-- pack.toml
|-- packs.lock
|-- assets/workflows/
|   |-- build-base/publish.md
|   `-- do-work/prepare-worktree.md
|-- docs/
|   |-- operations.md
|   `-- testing.md
`-- tests/test_city.py
```

The repository itself is the portable city source. Native Gas City state,
rig paths, Beads and Dolt data, worktrees, credentials, logs, and other
machine-local values stay outside tracked files.

## Native workflow

Follow [docs/operations.md](docs/operations.md) for native initialization,
the user-owned supervisor configuration link, lifecycle commands, rig binding,
gateway-only Discord import, service diagnosis, and the bounded official
Compound Engineering flow. [docs/testing.md](docs/testing.md) describes the
focused checks and the two manual live smokes.

## Governance and privacy

Keep one logical change per commit and human ownership of merges. Use ASCII
hyphens. Never commit private authorities, addresses, users, channels,
credential paths or hashes, runtime state, live prompts or responses, or
private pull-request payloads. Generic placeholders and `127.0.0.1` are
allowed. Review the staged file list and complete diff before committing.

## License and provenance

Local content is Apache-2.0. Imported upstream sources retain their licenses
and notices. See [LICENSE](LICENSE) and [PROVENANCE.md](PROVENANCE.md).
