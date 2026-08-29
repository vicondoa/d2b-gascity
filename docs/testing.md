# Testing

The repository has one focused, credential-free gate:

```text
python3 tests/test_city.py
make check
```

The standard-library test module validates:

- `cities/d2b-gascity` is the only active city root and the repository has no
  repository-local d2b checkout or bind mount declaration;
- the authored city files, reusable `packs/core-city` files, and absence of
  copied city, service, relay, binary, site, or runtime state;
- the pathless d2b `v3` rig declaration and native `gc rig add` contract;
- exactly four model tiers: `deep-thinker` with `gpt-5.6-sol` medium and
  `long_context`, `reviewer` with `grok-4.6` high and `long_context`,
  `solid-worker` with `gpt-5.6-luna` max and `long_context`, and
  `fast-worker` with `gpt-5.6-luna` medium and `default`;
- all twelve role assignments, the single city-local mayor, stock
  `builtin:codex` availability, and the absence of excluded providers and
  workflows;
- exact core, Beads, Gas City pack, and Discord import sources and pins;
- the Gas City pack city and rig import, global fragments, `v3` formula
  defaults, and full daemon settings;
- the local d2b Discord formula extension and governance fragment policy;
- Discord's native-service boundary and the absence of authored private
  mappings or credentials;
- source privacy, credential separation, and the no-token-coupling rule;
- documentation markers for the nested layout, clean reset contract,
  MIT cookbook provenance, and the unlicensed flake exclusion;
- native init and external rig binding when `GC_BIN` is supplied.

The checks do not start imported services or perform authenticated network
requests. They also assert that the retired local fragment and workflow
overrides are absent.

## Optional native smoke

Set `GC_BIN` to the pinned or host-supplied native executable:

```text
GC_BIN=/path/to/gc python3 tests/test_city.py
```

The smoke uses temporary generic homes and repositories and dummy `copilot`
and `codex` executables. It runs from an isolated copy of the nested city:

```text
gc init --file city.toml --preserve-existing --no-start .
```

It checks authored files, native import and configuration validation, the
resolved d2b Discord resume formula and the Gas City pack `build-basic` and
`implement` formulas, all twelve role-tier assignments, the documented
Discord command contracts with native `gc discord ... --help`, binds an
external fixture rig through `gc rig add`, and confirms that the rig path
stays in ignored `.gc/site.toml` state. The smoke does not start services or
use credentials.

## CI inputs

CI downloads exact pinned Linux archives for Gas City `v1.4.1`, Beads `v1.2.2`,
and Dolt `2.1.7`, verifies their SHA-256 values, and runs the focused test.
The workflow is [`.github/workflows/check.yml`](../.github/workflows/check.yml).
It does not require credentials, private network access, or live model or
GitHub activity.

## Manual live smokes

Authenticated ingress, Copilot CLI, optional Codex, Discord app setup, and
credentialed publication are live, redacted acceptance smokes. They require
host-local optional binaries, credentials, and network access and are not
committed test code, fixtures, reports, prompts, responses, or pull-request
payloads. The focused suite never starts Discord, Copilot, Codex, or an
external publication flow.

### Gas City pack

- Confirm native `gc status` shows the `gc.mayor` skill path and d2b rig
  roles including `run-operator`, `implementation-worker`, `publisher`, and
  `requirements-planner`.
- Inspect `build-basic`, `implement`, `review`, `publish`,
  `github-issue-fix`, and `github-pr-review` through native Gas City
  commands.
- Verify daemon patrol, restart-window, shutdown, and `formula_v2` settings
  from the rendered native configuration.
- Confirm the documented host branch-protection policy requires pull
  requests and applies to administrators. Treat it as defense-in-depth; this
  repository does not claim that the current host is already configured.
  Human-owned merge decisions remain the final boundary.

### Discord ingress and app policy

- Verify only `discord-interactions` is public, `discord-admin` remains
  tenant/access-policy protected, and `discord-gateway` remains private under
  `.gc/services/discord`. The official Discord pack owns all three services.
- Configure the Discord Interactions Endpoint URL as
  `https://<discord-interactions-public-url>/v0/discord/interactions` and
  verify signed requests are accepted only on that route.
- Import the default app with host-owned token input through `/dev/stdin`;
  verify guild, channel, and role allowlists, and keep token material mode
  `0600`.
- Enable Message Content Intent, then verify launcher and ambient-read
  traffic.
- Import a named chat app and verify its token, connection, bindings, and
  counters are isolated. Confirm named apps do not handle Interactions,
  workflow maps, or launcher rooms.
- Run command sync, verify the guild-scoped `/gc fix` command, submit its
  summary/context modal, and verify the fallback prompt path.
- Verify channel and rig mappings target `rig/implementation-worker` through
  `mol-d2b-discord-fix-issue`, which starts first-run work from `origin/v3`,
  resumes recorded branches safely, and retains the official Discord
  workflow.

### Discord chat and workflow

- Verify exact `bind-dm` and `bind-room` routing, managed thread inheritance,
  `mention_only`, `respond_all`, and `@@handle` launcher sessions.
- Verify ambient-read remains exact-targeted by default and that
  `--allow-untargeted-ambient-delivery` works only for one bound session.
- Verify direct-room peer fanout is opt-in, budget-limited, and retryable
  through `gc discord retry-peer-fanout`; verify launcher-managed fanout
  honors its configured limits and bot-authored messages are ignored.
- Verify `gc discord reply-current` replies with the same app and binding,
  while `gc discord publish` is the explicit human-visible path.
- Verify `gc discord post-message` projects workflow status and
  `gc discord release-workflow` clears a stuck workflow lock.
- Verify `gc discord status` and `gc discord status --json` omit token values,
  and restart `discord-gateway` after app rotation.
- Confirm agent output stays private until explicit publish and that replies
  are plain message bodies. Do not treat buttons, select menus, context
  menus, attachments, embeds, reactions, presence controls, or arbitrary
  slash commands as supported capabilities.

### PR-only publication

- Verify d2b work persists and re-reads `metadata.target=v3` and
  `metadata.merge_strategy=pr`.
- Verify publication refuses direct merges and never merges or force-pushes.

## Documentation and reset evidence

The focused gate checks documentation markers rather than running the
human-only reset. A reviewer must be able to distinguish:

1. portable source in `cities/d2b-gascity` and `packs/core-city`;
2. host-local `GC_CITY_PATH`, `.gc/site.toml`, mounts, credentials, mappings,
   bindings, launchers, and native runtime state;
3. the reset sequence: private preflight inventory, old root-city stop and
   unregister, bind-mount source confirmation, unmount without recursive
   deletion, preservation of the external checkout's product-local
   `.beads/`, `.gitignore`, and hooks, confirmed root-state cleanup, nested
   `gc init`, external `gc rig add`, and Discord re-import;
4. MIT provenance from `thinkjones/gascity-cookbook` and the statement that
   `rencire/gascity-flake` has no license and no content was copied.

Keep only redacted pass/fail notes outside this repository. Never save live
payloads, prompts, responses, credentials, identifiers, or service state.
