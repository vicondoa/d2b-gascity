# Operations

Gas City owns the city supervisor and its child lifecycle. The standalone
repository does not add a second lifecycle owner, a dashboard service, a
Discord sidecar, a publisher service, or a custom service declaration. The
publisher is a deterministic trusted subprocess launched by the supervisor's
one-shot agent lifecycle.

## Ordinary start

Bootstrap is not an ordinary-start hook. After a later deployment unit
installs the root service, the service starts the packaged supervisor with
`gc supervisor run`. It then performs delegated registration and
reconciliation using the machine-local site binding. Ordinary start must not
copy the prototype, rewrite portable files, or create a second user
supervisor.

The U3 operator check is explicit-path and state-preserving. If the supervisor
was stopped when the check began, a successful check enforces a stopped city
and a failed check best-effort restores it; a supervisor already running under
valid system delegation or the fixture guard is left running:

```text
python3 scripts/operator.py status \
  --state-root <state-root> \
  --city <city-root> \
  --rig <d2b-v3-checkout> \
  --gc <packaged-runtime>/bin/gc
```

`scripts/operator.py validate-request` only validates a small JSON status
request. It does not recreate old control-plane state or accept lifecycle
commands.

## Imports and source updates

`city/pack.toml` contains the Pack v2 root metadata and exact pinned imports
for the current Gas City core and Beads packs, Compound Engineering, and
Discord. The d2b rig composes the current gascity roles pack at rig scope.
`packs.lock` records the complete resolved closure.

Use the packaged runtime for validation:

```text
gc import check --city <city-root>
gc config show --city <city-root> --validate
gc lint <city-root>
gc doctor --city <city-root>
```

Upstream warnings from a stopped city, unavailable providers, or absent
supervisor are diagnostic context, not permission to weaken the portable
contract. Provider-specific readiness and local patches remain placeholders
until their owning units define them.

The resolved model-backed role graph is classified in
`city/role-provider-matrix.json`. The matrix is generated from the pinned
Pack v2 imports and every classified agent is patched to ACP with one of the
portable planning, review, or coding providers. Control and maintenance
agents remain subprocesses; the d2b publisher is the local
`d2b-gascity-publication-worker`, not a model-backed role.

Worktree creation is intentionally anchored to `origin/v3`. The core formulas
receive `base_branch = "v3"` through the d2b rig formula variables, and the
single higher-precedence Gas City worktree asset is recorded in
`city/worktree-producer-inventory.json`. The local asset cites the upstream
path and commit and replaces only remote-default branch discovery.
The inventory also records the exact current d2b `origin/v3` proof revision,
`db036097d05ede39009b912805a48f6ef8a74751`, in the local fake-repository
fixture. That fixture models only the `main` remote default, the `v3` branch,
and its revision marker; it does not copy d2b source or repository process
artifacts.

Discord operation is gateway-only in this city. The repository configures no
external publication edge, so the imported `discord-interactions` and
`discord-admin` processes may remain behind the supervisor without being
externally reachable. Do not patch those upstream service definitions or add a
Discord daemon.

Use the stopped helper with a root- or systemd-owned credential file:

```text
d2b-gascity-discord-import \
  --gc <runtime>/bin/gc \
  --state-root <state-root> \
  --city <city-root> \
  --token-file <credential-file> \
  --application-id <application-id> \
  --public-key <64-hex-public-key> \
  --guild-id <guild-id> \
  --channel-id <channel-id> \
  --operator-role-id <operator-role-id> \
  --operator-user-id <user-id>=<qualified-session>
```

The helper always supplies non-empty `--guild-allowlist`,
`--channel-allowlist`, and `--role-allowlist` values to the official
`gc discord import-app` command. The dedicated host-configured operator role
is the room boundary and must be assigned only to authorized operator users.
Direct operator DMs are explicit `gc discord bind-dm` bindings, one per
`--operator-user-id` mapping. Re-running the helper with the same application
ID imports a rotated token; restart the official gateway through the normal
Gas City operator path after rotation:

```text
gc service restart discord-gateway --city <city-root>
```

The helper passes the token through `/dev/stdin`, never argv or its output. It
requires an owner-only state root, rejects unsafe credential files, paths, IDs,
and session names before invoking `gc`, and does not echo child diagnostics.
Public Interactions publication and `sync-commands` are not invoked.

## Pull-request publication

After a validated `origin/v3` worktree has completed its required checks, Gas
City starts the packaged one-shot `d2b-gascity-publication-worker`. It is a
trusted subprocess with `prompt_mode=none`, `lifecycle=one_shot`, no ACP
session, and no model provider. It inherits the supervisor's
`CREDENTIALS_DIRECTORY`; no credential is passed to Copilot or any model
process.

The worker uses the official `gc gc claim` startup protocol (implemented by
the pinned CLI as `gc hook --claim --drain-ack --json`) and parses exactly one
normalized JSON result. A drain result exits. A work result is accepted only
when the rendered local `build-base` publish asset contains the exact machine
marker `gc.publication.worker_marker=d2b-gascity-publication-worker-v1` and
the rendered `gc.publication.push` and `gc.publication.open_pr` values. An
unrelated publisher task is rejected, and only the claimed bead is closed.
Continuation groups are claimed again; an empty group is acknowledged with a
runtime drain. A `claims_errored` drain is a typed retry failure and exits
nonzero, so the claim remains open for reconciliation.

The narrow prepare-worktree asset records and verifies on the real source
anchor the absolute `work_dir`, `gc.publication.base_ref=origin/v3`, and the
fresh `gc.publication.base_sha`. For enabled PR publication, the worker reads
`gc.input_convoy_id` from the workflow root. If that bead is a synthetic
drain-unit convoy, it uses `gc.drain_member_id` and never writes source state
to the synthetic bead. After claim, it verifies the source worktree is clean,
computes current `HEAD`, and sets `gc.publication.expected_head_sha` only when
the source anchor does not already contain it. A retry must match the existing
value exactly; a changed `HEAD` is rejected without overwriting the anchor.
The worker then invokes
`d2b-gascity-publish-pr <source-anchor-id>` from the source worktree.

The helper reads the immutable source anchor metadata
`work_dir`, `gc.publication.expected_head_sha`, `gc.publication.base_sha`, and
`gc.publication.base_ref=origin/v3`. It records the URL, SHA, and derived
branch with repeated `bd update <issue-id> --set-metadata key=value` options,
then performs an exact `bd show` readback before emitting its safe JSON record.
The worker records that URL, SHA, and branch plus the upstream-required
`gc.build.publish_*` metadata on both the workflow root and claimed step. It
writes a safe artifact under `GC_ARTIFACT_DIR` when available and never copies
child diagnostics or credentials into metadata, artifacts, or output.

The helper is hard-coded to `vicondoa/d2b` with base `v3` and accepts no
repository, base, branch, SHA, push-mode, merge, or bypass controls. It
refreshes and verifies `origin/v3`, proves the recorded base is an ancestor of
the clean expected head, and performs at most one create-only update of the
derived `gascity/*` branch. It rejects Git replacement refs and nonempty graft
files before mutation. After credential-free worktree validation, it imports
the exact head into a mode-0700 temporary bare repository and performs every
credentialed fetch, `ls-remote`, and push from that repository using the
verified direct HTTPS URL. Closed, merged, duplicate, conflicting, or
malformed records stop publication.

Before any network operation, the helper reads every fetch and push URL with
`git remote get-url --all origin` and `git remote get-url --push --all origin`.
Each side must have exactly one identical, credential-free HTTPS URL for
`https://github.com/vicondoa/d2b` or its `.git` spelling. It uses that verified
URL directly for fetch, `ls-remote`, and push with the dedicated token
environment. Child Git configuration disables hooks, helpers, proxy use, TLS overrides, and
`push.followTags`;
the only push is one SHA-to-`refs/heads/gascity/<work-id>` refspec without
force or force-with-lease.

Host configuration sets
`services.d2bGasCity.credentials.githubPublicationTokenFile` and
`services.d2bGasCity.credentials.githubPublicationPolicyFile` to
administrator-controlled absolute source paths. The Gas City systemd unit
projects those sources under the fixed credential names
`github-publication-token` and `github-publication-policy`, and systemd
provides their credential directory through `CREDENTIALS_DIRECTORY`. The
helper reads only those names from that directory; arbitrary caller-selected
paths and environment overrides are not accepted.

Host acceptance requires an administrator to review the repository rules and
the least-privilege publication identity against the exact policy, keep the
policy source non-writable, and keep the token source private. The helper
gives `gh` the dedicated publication token and gives Git remote operations a
GitHub authorization header through a child-only Git configuration. Both
subprocess environments use a nonexistent home, disabled terminal prompts,
system-config suppression, a minimal path, and no ambient GitHub, SSH, or
unrelated secret variables.

The documented host acceptance check is performed before installing the
attestation:

```text
gh api repos/vicondoa/d2b --jq '{name: .full_name, permissions: .permissions}'
gh api 'repos/vicondoa/d2b/branches/v3/protection'
gh api 'repos/vicondoa/d2b/rulesets?includes_parents=true'
stat -c 'uid=%u mode=%a' "$configured_publication_policy_source"
```

The first three reads are run with the dedicated publication identity and
must document create-only `gascity/*` branches, no `v3` update, no force
update, no merge or queue authority, and no bypass actor. The final check
must report the expected host ownership and no write bits. Do not copy either
credential into the repository or encode a fixed deployment path in source.
Pack-native behavior includes application and public-key validation, role,
guild, and channel policy, signed-interaction timestamp rejection at the
pack's retention window, duplicate interaction receipts, bot/self filtering
in the gateway, and two retries for Discord API rate-limit responses. The
pack does not provide a configurable inbound rate limiter or a direct room
user allowlist; the host role plus explicit DM bindings are the supported
substitute.

## Machine-local state

The repository contains no rig path, `.gc/site.toml`, cities registry, Beads
metadata, Dolt database, credential, host unit, or service state. The
explicit state root and city path supplied to bootstrap are deployment
inputs. In the NixOS deployment, `--state-root` is the service's
`GC_HOME`, `/var/lib/d2b-gascity/gc`; bootstrap therefore keeps Dolt at
`/var/lib/d2b-gascity/gc/dolt` and the global Git config at
`/var/lib/d2b-gascity/gc/gitconfig`. Keep these paths outside the portable
source and protect them with the host's normal ownership and backup policy.
