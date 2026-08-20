# Testing

The repository has one focused, credential-free check:

```text
python3 tests/test_city.py
make check
```

`make check` runs the same standard-library test module. It validates the
root Pack v2 layout, the d2b `v3` rig declaration, the stock Codex provider,
canonical import pins including Slack Full, the two `v3` workflow overrides,
the absence of city-owned dashboard proxy services, source privacy, credential
separation, and the native init and rig-binding path when `GC_BIN` is
available.

The focused checks also assert that Slack remains an imported source-only
pack: no Slack service or built adapter binary is authored by the city. They
cover host environment inheritance (`GC_CITY_NAME`, `GC_CITY_PATH`, and the
host-supplied `GC_API_BASE_URL`), the stock `slack-v0` fragment and
`gc slack reply-current` path, and the removal of the old
`GH_TOKEN=$COPILOT_GITHUB_TOKEN` coupling.

## Optional native smoke

Set `GC_BIN` to the pinned or host-supplied native executable:

```text
GC_BIN=/path/to/gc python3 tests/test_city.py
```

The smoke uses temporary generic homes and repositories and a dummy `codex`
executable. It runs `gc init --file city.toml --preserve-existing --no-start
.`, checks the authored files, performs native import/config validation, binds
a fixture rig, and confirms that the rig path stays in ignored
`.gc/site.toml` state.

## CI inputs

CI downloads exact pinned Linux archives for Gas City `v1.4.1`, Beads `v1.2.2`,
and Dolt `2.1.7`, verifies their SHA-256 values, and runs the focused test.
The workflow is [`.github/workflows/check.yml`](../.github/workflows/check.yml).
It does not require credentials, network access to a private repository, or
live model, Discord, or GitHub activity.

## Manual live smokes

Authenticated ingress, routed Codex, Slack clarification, and credentialed
Compound Engineering to a pull request are live, redacted acceptance smokes.
They require site-local optional binaries, credentials, and network access and
are not committed test code, fixtures, reports, prompts, responses, or
pull-request payloads. The focused suite never starts Slack, Codex Router, or
an external pull-request flow.

- Cloudflare dashboard: with the `cloudflared` connector running, verify an
  unauthenticated request to the dashboard hostname is rejected by Cloudflare
  Access before reaching the host. Verify the allowlisted operator can load
  the dashboard, perform an API mutation, receive SSE updates, and use any
  required WebSocket upgrade.
- Cloudflare Slack route: verify the separate Slack hostname reaches only
  `/slack/events`, does not require Cloudflare Access login, and preserves
  Slack signing-secret and workspace validation. Keep the adapter on
  `127.0.0.1:8765` and do not open a home inbound port.
- Ingress: with the host-owned Cloudflare connector running, verify the
  dashboard is authenticated by Access, direct native SPA/API/SSE access
  works, and no home inbound port is open.
- Slack: source the mode-`0600`
  `${XDG_CONFIG_HOME:-$HOME/.config}/gc-slack-adapter/env` file in the same
  shell as `gc start`; verify the host-supplied `GC_CITY_NAME`,
  `GC_CITY_PATH`, and `GC_API_BASE_URL` values are inherited by the imported
  `proxy_process`. Bind only the operator-verified one-to-one DM, attach the
  stock `slack-v0` fragment, and verify one question and one
  `gc slack reply-current` answer. Do not use Slack mocks or add delivery
  verification.
- Compound Engineering: run the bounded `gc sling gc.run-operator` example
  from [operations.md](operations.md), verify the worktree starts at
  `origin/v3`, and verify the official pull request targets `v3` in
  `vicondoa/d2b`. Stop on any mismatch and retain only redacted pass/fail
  notes outside the repository.
