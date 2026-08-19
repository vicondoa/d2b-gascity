# Provenance

## Extraction source

The standalone repository begins from a clean source snapshot of
`vicondoa/d2b` at provenance commit `9e0abd0c`. This records source authority
only. It does not import the d2b repository's full history, identities, tags,
worktrees, or runtime state.

The repository contains reviewed Gas City city configuration, not a fork of
the d2b product. The root files are authored for this city. The workflow
assets are narrow local overrides for the non-default d2b `v3` base; they do
not copy product source or upstream pack implementation.

## Upstream inputs

| Component | Source | Pin | License or terms |
| --- | --- | --- | --- |
| Gas City | [gastownhall/gascity](https://github.com/gastownhall/gascity) | `v1.4.1`, `f895c0ff47d6ee9334ed282a416387eb5b084d24` | MIT |
| Gas City packs | [gastownhall/gascity-packs](https://github.com/gastownhall/gascity-packs) | `5d2a9d023edbb9ba24fdcff554e89fc3d7da72fe` | Retain upstream notices and verify pack terms before redistribution |
| Beads | [steveyegge/beads](https://github.com/steveyegge/beads) | `v1.2.2`, `6c124203e771433a3550c348771a5b5e27fd3c21` | MIT |
| Dolt | [dolthub/dolt](https://github.com/dolthub/dolt) | `2.1.7` | Apache-2.0 |
| Copilot CLI | [github/copilot-cli](https://github.com/github/copilot-cli) | `1.0.79` | GitHub Copilot CLI License |

The Gas City and Beads pack imports are recorded in `pack.toml` and
`packs.lock`. Optional runtime and proxy installation provenance belongs to
the separate `vicondoa/gascity.nix` repository or the compatible host source
that supplies those binaries.

## License boundary

Local repository content is provided under the Apache License, Version 2.0.
Imported packs and binaries retain their upstream licenses and notices.
Nothing in this file relicenses an imported component.

## State and privacy boundary

Only reviewed portable source is tracked. Never copy into this repository:

- full d2b history, unrelated product code, worktrees, or copied checkout
  state;
- `.gc`, `.beads`, Dolt databases, sessions, caches, sockets, reports, logs,
  or service dumps;
- credentials, tokens, keys, cookies, password hashes, private paths,
  authorities, addresses, users, channels, or host configuration;
- live prompts, model responses, or private pull-request payloads.

Generic placeholders and `127.0.0.1` are permitted where needed for portable
topology examples and tests.
