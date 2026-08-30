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
- the pathless d2b `v3` and city-source `main` declarations, machine-local
  bindings, and native `gc rig add` provisioning contract;
- exactly four model tiers: `deep-thinker` with `gpt-5.6-sol` medium and
  `long_context`, `reviewer` with `grok-4.6` high and `long_context`,
  `solid-worker` with `gpt-5.6-luna` max and `long_context`, and
  `fast-worker` with `gpt-5.6-luna` medium and `default`;
- all twelve role assignments on both rigs, the single city-local mayor, stock
  `builtin:codex` availability, and the absence of excluded providers and
  workflows;
- exact core, Beads, Gas City pack, and Discord import sources and pins;
- the Gas City pack city and rig imports, global fragments, repository-specific
  formula defaults, and full daemon settings;
- the local d2b Discord formula extension and governance fragment policy;
- the rig-imported `pr-babysit` Pack v2, binding-qualified babysitter
  identities, workdir-local dual Copilot projection, mandatory prompt gate,
  publication handoff and verification receipt, Beads watch/action state,
  `1m` checkpoint order, action-blocks-watch dependency, and Formula v2 repair;
- the complete authored-file inventory for every U1-U6 local pack surface;
- target-only d2b `v3` and city-source `main` behavior, including the
  no-`update-branch` v1 boundary, retry and time budgets, terminal/rearm and
  ambiguous-push handling, and human merge ownership;
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
`implement` formulas, all twelve role-tier assignments on both rigs, and the
documented Discord command contracts. It pre-seeds a separate city-source
fixture in `.gc/site.toml`, provisions both fixture rigs through native
`gc rig add`, and confirms that paths stay in ignored site state. The smoke
does not start services or use credentials.

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

The committed configuration has no service change, daemon, webhook, relay,
custom provider, separate custom publication machinery, merge, force-push or
`--force-with-lease`, raw rebase, workflow approval, replacement PR, private
evidence, or runtime state. Native Gas City owns lifecycle and the
rig-imported pack owns only its bounded checkpoint and repair seams.

### PR babysitting

The enabled smoke exercises the rig-imported `pr-babysit` pack through the
native surfaces, not a separate service:

```text
gc config show --json
gc config explain --rig d2b --agent pr-babysitter
gc skill list --agent d2b/pr-babysit.pr-babysitter --json
gc skill list --agent city-source/pr-babysit.pr-babysitter --json
gc formula show mol-pr-babysit-repair --rig d2b --json
```

The workdir-local projection must contain the exact vendored commit in both
`.github/skills/pr-babysit` and `.agents/skills/pr-babysit`. The babysitter's
mandatory projection gate is the first action and fails closed before `gh`,
Git, or a push. Publication uses one deterministic receipt:

```text
gc pr-babysit pr-babysit publication-handoff \
  --rig d2b --publication-bead-id <publication-bead-id> \
  --url <pull-request-url> --pr-number <number> --json
gc pr-babysit pr-babysit verify-handoff \
  --rig d2b --publication-bead-id <publication-bead-id> \
  --url <pull-request-url> --pr-number <number> --json
```

The handoff result must show
`target=<rig>/pr-babysit.pr-babysitter` and store it as `handoff_target` in
receipt metadata. The watch record must show
`base_ref=v3` for d2b or `base_ref=main` for city-source. The publication
bead must show `merge_strategy=pr`; its `metadata.target=v3` or
`metadata.target=main` is publication metadata, not the handoff routing
target.

The cooldown smoke invokes the canonical bounded state action and verifies
that it lists, rechecks, and routes due watches in deterministic order:

```text
gc pr-babysit pr-babysit sweep --rig d2b --limit 32 --json
```

Credential-free tests use fake GitHub, Beads, and Gas City commands to cover
both d2b/`v3` and city-source/`main`: duplicate handoff, one-writer action
claims, fresh checkpoint ordering, feedback-before-CI, current-head repair,
`bd dep <action-id> --blocks <watch-id>`, restart recovery, retry exhaustion,
terminal state, explicit `rearm=true`, ambiguous push blocking, and
same-repository-only repair. They do not mutate GitHub or use credentials.

The first version does not call `update-branch`. Repair requires an
operator-attested identity with Contents write and Pull requests read only;
the agent cannot introspect fine-grained permissions. Pull requests write,
merge/admin, workflow-approval, and Copilot Requests authority are refused.
Keep publication, repair GitHub, Copilot Requests, and Discord credentials
separate, and never reuse a Copilot token for `GH_TOKEN` or `GITHUB_TOKEN`.
Before a repair, require `PR_BABYSIT_VALIDATOR` as an absolute, non-symlink,
executable file and set
`PR_BABYSIT_VALIDATOR_ATTESTED=credential-isolated-v1`. It must run
`make check` in a credential- and network-isolated environment. A missing
validator blocks repair, as do an invalid or failed validator. Fork or
cross-repository PRs are human blockers in v1.
The credential-free `gc pr-babysit pr-babysit check-credentials --json`
command verifies the operator capability and validator attestations plus
token separation only; it does not replace the validator run.

d2b is enabled first. The `city-source` rig remains suspended-on-start and
must not be enabled for live repair until the U8 disposable d2b acceptance
passes. Live authenticated evidence is private and redacted; retain only
safe pass/fail notes outside this repository. No live U8 acceptance is claimed
by this source tree.

### Human-gate recovery

The existing `gate-sweep` remains the native mechanical gate sweep. Human-gate
notification and stale-gate re-notification are outside the `pr-babysit`
target-only capability. Do not create a city-owned watcher, relay, scheduler,
or delivery verifier to change that boundary.

If the native core later exposes those orders, a host-owned redacted smoke may
use disposable Beads and notification fixtures to verify creation notification,
interval-bounded stale re-notification, failed-send retry, resolution stop, and
restart recovery from durable state. Keep recipient mappings, gate
identifiers, notification bodies, runtime state, and delivery evidence
host-local.

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

- Verify the handoff receipt's
  `target=<rig>/pr-babysit.pr-babysitter`, the watch's
  `base_ref=v3` or `base_ref=main`, and the publication bead's
  `metadata.merge_strategy=pr` plus `metadata.target=v3` for d2b or
  `metadata.target=main` for city-source.
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
