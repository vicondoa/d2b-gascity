# Model tiers

The portable city keeps model policy in four reusable aliases. Tier data is
authored in `packs/core-city/model-tiers.base.toml` and projected into
`cities/d2b-gascity/model-tiers.toml`. The projection is deterministic and
contains role patches only; it does not contain credentials, paths, runtime
state, or private mappings.

## Tier definitions

| Tier | Stock provider | Model | Effort | Context |
| --- | --- | --- | --- | --- |
| `deep-thinker` | `builtin:copilot` | `gpt-5.6-sol` | `medium` | `long_context` |
| `reviewer` | `builtin:copilot` | `grok-4.6` | `high` | `long_context` |
| `solid-worker` | `builtin:copilot` | `gpt-5.6-luna` | `max` | `long_context` |
| `fast-worker` | `builtin:copilot` | `gpt-5.6-luna` | `medium` | `default` |

The city workspace uses `deep-thinker`. The tier aliases select stock
Copilot CLI provider profiles; they are not custom adapters or transport
implementations. Stock `builtin:codex` remains declared as an explicit
alternate provider only. It is not one of the four tiers and is not assigned
by default.

## Deterministic role map

The imported `gascity/roles` agents are assigned as follows:

| Tier | Roles |
| --- | --- |
| `deep-thinker` | `requirements-planner`, `design-author`, `task-decomposer` |
| `reviewer` | `design-implementation-reviewer`, `design-test-risk-reviewer`, `implementation-reviewer`, `gap-analyst`, `review-synthesizer`, `issue-triager` |
| `solid-worker` | `implementation-worker` |
| `fast-worker` | `run-operator`, `publisher` |

The city-local mayor also uses `deep-thinker`. This map is the only role
routing policy authored by the city. It keeps planning, review, coding, and
mechanical execution distinct while leaving lifecycle ownership with native
Gas City.

## Generation and review

From the nested city directory, regenerate the projection only when the
base tier data or city source changes:

```text
gc core-city gen-model-tiers city.toml > model-tiers.toml
```

Review the generated diff and run:

```text
python3 tests/test_city.py
```

Do not add a role-specific credential, `command`, `env`, router URL, host
path, or private payload to a tier. Copilot Requests, d2b publication, and
Discord app credentials remain separate host-owned concerns.
