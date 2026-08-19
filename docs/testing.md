# Testing

The repository has one focused, credential-free check:

```text
python3 tests/test_city.py
make check
```

`make check` runs the same standard-library test module. It validates the
root Pack v2 layout, the d2b `v3` rig declaration, canonical import pins,
the two `v3` workflow overrides, proxy service declarations, source privacy,
and the native init and rig-binding path when `GC_BIN` is available.

## Optional native smoke

Set `GC_BIN` to the pinned or host-supplied native executable:

```text
GC_BIN=/path/to/gc python3 tests/test_city.py
```

The smoke uses temporary generic homes and repositories. It runs
`gc init --file city.toml --preserve-existing --no-start .`, checks the
authored files, performs native import/config validation, binds a fixture rig,
and confirms that the rig path stays in ignored `.gc/site.toml` state.

## CI inputs

CI downloads exact pinned Linux archives for Gas City `v1.4.1`, Beads `v1.2.2`,
and Dolt `2.1.7`, verifies their SHA-256 values, and runs the focused test.
The workflow is [`.github/workflows/check.yml`](../.github/workflows/check.yml).
It does not require credentials, network access to a private repository, or
live model, Discord, or GitHub activity.

## Manual live smokes

Authenticated ingress and credentialed Compound Engineering to a pull request
are live, redacted acceptance smokes. They require site-local optional
binaries, credentials, and network access and are not committed test code,
fixtures, reports, prompts, responses, or pull-request payloads.

- Ingress: with host-provided proxy configuration, verify listeners are absent
  before `gc start`, authentication fails closed, authenticated SPA/API/SSE
  access works, and listeners disappear after `gc stop`.
- Compound Engineering: run the bounded `gc sling gc.run-operator` example
  from [operations.md](operations.md), verify the worktree starts at
  `origin/v3`, and verify the official pull request targets `v3` in
  `vicondoa/d2b`. Stop on any mismatch and retain only redacted pass/fail
  notes outside the repository.
