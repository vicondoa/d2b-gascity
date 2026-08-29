# Builtin Copilot CLI and Codex Providers

Authority: `docs/plans/2026-08-27-001-feat-copilot-cli-provider-plan.md`.

## Decision

This city declares both stock Gas City providers and defaults to Copilot CLI.

| Provider | Base | Role |
| --- | --- | --- |
| `copilot-planning-grok` | `builtin:copilot` | Workspace default. Planning and primary review. |
| `copilot-code-luna` | `builtin:copilot` | d2b implementation-worker coding lane. |
| `codex` | `builtin:codex` | Alternate stock provider. Not the workspace default. |

Agents run the host-supplied `copilot` command unless an operator or patch
selects `codex`. Do not add a custom adapter, ACP shim, wrapper `command`,
or router URL.

## Copilot lanes

| Lane | Provider name | Model | Context | Effort | Used by |
| --- | --- | --- | --- | --- | --- |
| Planning and primary review | `copilot-planning-grok` | `grok-4.6` | `long_context` | `high` | Workspace default, including `gc.mayor` and review roles |
| Coding | `copilot-code-luna` | `gpt-5.6-luna` | `default` | `max` | d2b `implementation-worker` only |

Luna may review only when Grok is explicitly unsupported or unavailable. That
fallback is an operator exception, not a second committed Copilot provider.

## Codex alternate

`providers.codex` is the stock builtin Codex profile with an empty model
default. The host may supply `codex` and, if desired, Codex Router. The city
does not require Codex Router for the Copilot default path.

To run a Gas City pack agent on Codex instead of the Copilot default, patch
that agent to `provider = "codex"`. Do not change the workspace default.

## City shape

```toml
[workspace]
provider = "copilot-planning-grok"

[providers.copilot-planning-grok]
base = "builtin:copilot"
args = ["--yolo", "--model", "grok-4.6", "--context", "long_context", "--effort", "high"]

[providers.copilot-code-luna]
base = "builtin:copilot"
args = ["--yolo", "--model", "gpt-5.6-luna", "--context", "default", "--effort", "max"]

[providers.codex]
base = "builtin:codex"
ready_delay_ms = 0
[providers.codex.option_defaults]
model = ""

[[patches.agent]]
dir = "d2b"
name = "implementation-worker"
provider = "copilot-code-luna"
```

Copilot lane flags live in `args` because builtin Copilot has no model
`option_defaults` schema. Copilot provider blocks omit `env`, `command`, and
`option_defaults`. Codex keeps its empty model option so a host router or
Codex default can supply the model.

The `implementation-worker` patch is the only coding-lane override. It
selects Luna on the Copilot default path.

## Credential boundary

Builtin Copilot reads `COPILOT_GITHUB_TOKEN` from the host environment.
The city does not declare that variable, a Copilot token path, or
`GH_TOKEN`. Codex credentials stay on the host Codex or router path.

Keep these credentials separate:

- Copilot Requests for Copilot CLI inference
- Codex or Codex Router credentials when that provider is used
- d2b publication GitHub authorization
- Discord app tokens in host-managed Discord state

Never set `GH_TOKEN` from a Copilot token.

## Host boundary

`vicondoa/gascity.nix` or another compatible host source installs `gc`,
`copilot`, optional `codex`, and `gh`. This repository does not package those
binaries or start a Copilot or Codex service.

Optional native smoke may place dummy `copilot` and `codex` executables on
`PATH`. Live authentication stays a redacted manual smoke.

## Non-goals

- Custom Copilot or Codex adapters
- Making Codex the workspace default
- Per-role Copilot profiles beyond the d2b implementation-worker
- City-owned Discord, relay, or publication machinery
- Committed prompts, model responses, or live evidence
