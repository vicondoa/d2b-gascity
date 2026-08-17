# Standalone Gas City architecture

The NixOS module in this repository owns one Gas City lifecycle boundary. The
module is exported as `nixosModules.gasCityContributor` and is enabled with
`services.d2bGasCity`.

## Lifecycle

The enabled core declares one long-lived unit:

```text
d2b-gascity.service
  User=d2b-gascity
  ExecStart=<gas-city-contributor>/bin/gc supervisor run
  GC_SUPERVISOR_SYSTEMD_UNIT=d2b-gascity.service
  GC_SUPERVISOR_SYSTEMD_SCOPE=system
```

The module also declares a socket-activated API compatibility proxy. It is
deployment infrastructure, not a second Gas City lifecycle owner:

```text
uid 41080 CLI process
  -> 127.0.0.1:18372
       d2b-gascity-api-proxy.socket
         d2b-gascity-api-proxy.service
           systemd-socket-proxyd
             -> 127.0.0.1:8372
```

This byte-forwarding route is the no-upstream-patch compatibility shim for
upstream #5262. The proxy runs as `d2b-gascity` and never starts, stops, or
reconciles the supervisor. An nftables output rule permits only uid 41080 to
connect to port 18372, so it is not a host-wide local API or dashboard ingress.
Remove it when upstream provides identity-aware standalone API routing.

`KillMode=control-group` makes the service cgroup the ownership boundary for
the supervisor and all of its upstream-managed children. The module does not
declare a Dolt unit, dashboard unit, controller unit, Discord unit, ACP unit,
or per-child lifecycle sidecar. Gas City starts and reconciles those children
itself. Bootstrap is an operator command, not `ExecStartPre`; an empty registry
is a valid service state.

ACP sessions use a named tmux server `tmux -L d2b-gascity`. Upstream treats a
missing server as a failed observation rather than an empty city, so the
supervisor unit starts that server in the same sandbox before `gc supervisor
run` and points `TMUX_TMPDIR` at `/run/d2b-gascity`. This is not a second
lifecycle owner. ACP identity sidecars stay under the private `TMPDIR=/tmp`.

The persistent layout is fixed and intentionally separate from the retired
prototype:

```text
/var/lib/d2b-gascity/
  city/
  rigs/d2b/
  gc/
  home/
  config/
  state/
  cache/
```

Systemd `StateDirectory` and tmpfiles create the parent and known child
directories with restrictive ownership and modes. `GC_HOME` is
`/var/lib/d2b-gascity/gc`, and the machine-local supervisor configuration is
bound into `GC_HOME/supervisor.toml`. The portable city and scripts are
installed by the contributor package below `share/d2b-gascity`; the
`d2b-gascity-bootstrap` and `d2b-gascity-operator` wrappers are available to
the configured operator group.

## Supervisor configuration

The supervisor always binds to the fixed `127.0.0.1:8372` listener. Remote
dashboard mode requires a host-supplied hostname, which is emitted as the sole
`allowed_hosts` entry. The generated file never sets `allowed_origins`,
`allow_mutations`, `write_auth_*`, or `read_auth_*`. There is no non-loopback
supervisor option.

The portable city also contains:

```toml
[api]
bind = "127.0.0.1"
port = 18372
```

This is the standalone CLI endpoint used by the compatibility route. The
supervisor may ignore this city API port and continues to own 8372.

Managed Dolt uses upstream dynamic allocation by default. A fixed
`dolt.fixedPort` is optional; when selected, it must be distinct from every
other listener and receives a matching Gas City owner rule. Dynamic Dolt
ports are never placed in the firewall.

## Copilot ACP providers

The portable city declares five direct ACP provider names:

- `copilot-planning-grok` uses `grok-4.6`, `long_context`, and `high`.
- `copilot-review` uses the machine-local readiness selection.
- `copilot-review-grok` and `copilot-review-luna` are explicit diagnostic
  profiles.
- `copilot-code-luna` uses `gpt-5.6-luna`, `default`, and `max`.

The portable workspace default is `copilot-review`, so unpatched workspace
agents receive the machine-selected provider without overriding explicit
agent patches. The imported city-scoped `bd.dog` agent is the deliberate
control exception: its exact patch sets `suspended = true` and leaves
provider and session unset. This keeps the city and supervisor available
without background ACP model work while the rig is idle; an explicit
operator resume uses the workspace fallback provider.

Every provider invokes the packaged
`d2b-gascity-copilot-provider` wrapper. It is one stateless parent per ACP
session, starts the exact sibling `copilot` executable directly, inherits
stdio for normal sessions, and forwards termination signals to the child
process group. It never creates a provider daemon, transport endpoint, session
store, retry ledger, or second lifecycle owner.

The wrapper contains a narrow deployment shim for the pinned upstream ACP
identity handoff. At the beginning of `run`, when `GC_SESSION_NAME` is
non-empty, it writes the non-empty `GC_SESSION_ID`, `GC_INSTANCE_TOKEN`, and
`GC_RUNTIME_EPOCH` values to the upstream ACP sidecar directory. The file names
use the upstream SHA-256 session and key hashes, and each file is replaced
through a flushed temporary file with mode `0644`; the directory is mode
`0755`. The NixOS service sets `TMPDIR=/tmp` inside the unit's `PrivateTmp`
namespace, so upstream Go `os.TempDir()` and wrapper Python
`tempfile.gettempdir()` both resolve to the same `/tmp/gc-acp` directory.

This is a deployment shim, not an upstream Gas City patch. It seeds no other
environment value or credential, rejects control characters and oversized
identity values, and never removes identity files. Upstream ACP `Stop` owns
sidecar cleanup; a later incarnation atomically overwrites stale values. The
related orphan behavior is tracked upstream in
[#4714](https://github.com/gastownhall/gascity/issues/4714). Remove this shim
when upstream ACP seeds identity itself.

The wrapper reads only the systemd-projected Copilot credential after checking
that it is a regular file with no symlink and exactly `0400` or `0440`
permissions. Systemd projections may remain root-owned; explicit
`--credential-file` paths must remain owned by the service identity and keep
owner-read access with no group/other access or execute bits. The child
receives only `COPILOT_GITHUB_TOKEN` from the credential projection. A private
`COPILOT_HOME/settings.json` is created below `XDG_RUNTIME_DIR` for each
process and removed after the child exits.

The settings file enables the Copilot CLI experimental MXC sandbox, grants the
current worktree, permits outbound dependency traffic while blocking local
network access, sandboxes local MCP and LSP processes, disables GitHub and git
credential injection, and denies credential, service-state, NixOS, SSH, and
key paths. Built-in file edits remain policy-bound rather than a perfect
operating-system boundary: imported prompts and supervisor children still
share the dedicated Gas City identity. This residual same-identity trust is
mitigated by exact pins, scrubbed child environment, closed tool policies, and
the no-bypass sandbox setting.

When a Copilot credential is configured, `d2b-gascity.service` runs one
bounded no-tools readiness sequence before `gc supervisor run`. It probes
coding Luna first, then review Grok. Only typed Grok `unsupported` or
`unavailable` results permit a review Luna probe. Authentication, network,
quota, malformed, timeout, closed, and unknown results keep readiness
blocked. The result is atomically written owner-only to
`/var/lib/d2b-gascity/config/provider-selection.json`; no model response or
credential is persisted. Without a Copilot credential, no readiness command
is added and the service remains valid.

## Pull-request publication credentials

The one-shot `d2b-gascity-publication-worker` is the only publication path.
The service projects the exact policy credential and exactly one authentication
mode into `CREDENTIALS_DIRECTORY`: the legacy static
`github-publication-token`, or the preferred
`github-publication-app-key` and `github-publication-app-config` pair. The
policy is required whenever any publication credential is configured. The App
config has no host path or secret and must be exactly:

```json
{
  "version": 1,
  "app_id": 123456,
  "installation_id": 789012,
  "repository": "vicondoa/d2b"
}
```

The PEM app key is private and accepts only projected mode `0400` or `0440`.
The helper first tries the static token for compatibility. Only a missing
static projection permits fallback to an on-demand GitHub App flow. That flow
builds a JWT with `RS256`, `iat=now-60`, `exp=now+540`, and the decimal app ID,
then invokes the packaged OpenSSL through the key path with the signing input
on standard input. It requests only `metadata:read`, `contents:write`, and
`pull_requests:write` for `vicondoa/d2b`, and rejects broader permissions,
unexpected repositories, invalid token text, or an expiry outside the bounded
future window.

The installation token exists only in the helper process and child GitHub
environments. It is never written to disk, metadata, artifacts, logs, or JSON
publication records. There is no token cache, daemon, refresh timer, or
supervisor restart coupling; each publication attempt mints a current token.

## Optional remote dashboard ingress

When `dashboard.remote.enable` is false, no TinyAuth or relay unit, credential,
listener, or source-admission rule is declared. When it is true, exactly two
separate infrastructure units are added:

```text
external TLS proxy
  -> https://<authHostname>:443
       d2b-gascity-relay.service:<authPort>
         -> 127.0.0.1:<tinyauthPort>
  -> https://<hostname>:443
       d2b-gascity-relay.service:<relayPort>
         auth_request -> 127.0.0.1:<tinyauthPort>
         proxy_pass  -> 127.0.0.1:8372
```

The dashboard hostname is the supervisor dashboard/API authority. The
distinct auth hostname is TinyAuth's authority and must be its subdomain so
the browser accepts the shared parent-domain session cookie. The public authorities are
HTTPS on port 443; the listener ports above are private deployment inputs.
There is no public HTTP option. TinyAuth uses the auth hostname as its
application URL, enables split-host subdomain cookie behavior, and stores
sessions in persistent SQLite state under
`/var/lib/d2b-gascity-tinyauth` via `StateDirectory`. A TinyAuth restart
therefore does not discard otherwise-valid sessions.

The relay and TinyAuth units have separate unprivileged identities and are
not `PartOf` the Gas City service. The relay `Wants` TinyAuth and orders after
it rather than requiring it, so a stopped TinyAuth rotation leaves the relay
running and fail-closed; restarting TinyAuth restores auth without a relay
restart. They cannot launch or restart Gas City.
Nginx exposes one auth server and one dashboard server on the relay address.
The auth server proxies all TinyAuth root-relative routes, assets, and API
requests to the raw loopback port. The dashboard server authenticates every
dashboard, API, asset, and SSE route before forwarding and preserves the
external dashboard `Host`, `Origin`, `Sec-Fetch-Site`, native `X-GC-Request`,
method, body, cookies, SSE behavior, and `Last-Event-ID`. It forwards
TinyAuth's `X-Tinyauth-Location` for exact deep-link login redirects and
copies session-refresh `Set-Cookie` headers. It overwrites untrusted identity
headers and synthesizes canonical `X-Forwarded-Proto=https`,
`X-Forwarded-Port=443`, and listener-specific `X-Forwarded-Host` values; Gas
City does not authorize from those headers.

Unsafe dashboard methods require the exact `https://<hostname>` Origin and
`Sec-Fetch-Site: same-origin`. Unsafe TinyAuth methods mirror the production Origin/Referer guard:
an unsafe request with a bad Origin is denied, a request with neither
Origin nor Referer is denied, and a request with no Origin plus a bad Referer
is denied. Missing native `X-GC-Request` is passed through so Gas City can
apply its own rejection.

Both relay listener ports are admitted only on the configured interface and
trusted external proxy CIDRs. Nginx evaluates a source-admission `geo` map in
rewrite phase before Host handling and retains `allow`/`deny` as defense in
depth. A loopback owner policy permits the supervisor port to be reached by
the Gas City identity and relay identity only. The separate API compatibility
port is admitted only to the Gas City uid 41080. TinyAuth's raw loopback port
accepts connections only from the relay identity. The shared Gas City identity
remains a deliberate trust boundary because upstream children legitimately use
the supervisor API.

TinyAuth users are loaded through systemd `LoadCredential`. Credential values
are never serialized into unit environment text. The exact TinyAuth and Nginx
packages come from contributor-package passthrough values or explicit package
options.

No mTLS is used between the same-host relay and supervisor. The residual risk
is limited to private HTTP on the host and the correctness of source
filtering. A deployment that needs a public supervisor bind or stronger
backend identity requires a separate design.

## Sandbox

The Gas City unit and ingress infrastructure use empty capability bounding and
ambient sets, `NoNewPrivileges`, private temporary and device namespaces,
protected home, system, kernel, control-group, clock, hostname, and proc
surfaces, restrictive `UMask`, `RestrictSUIDSGID`, `LockPersonality`, bounded
CPU, memory, swap, and task resources, and only Unix, IPv4, and IPv6 address
families. Writable paths are explicit. No syscall allowlist is imposed: Gas
City remains responsible for launching its upstream-managed Dolt and child
processes without a policy that silently breaks them.

The resolved model-backed role graph is kept in
`city/role-provider-matrix.json`; it is a generated audit surface rather than
a copy of upstream agent definitions. Core worktree formulas use the d2b rig's
`base_branch = "v3"` formula variable. The only prompt override is the
worktree preparation asset recorded in
`city/worktree-producer-inventory.json`, which replaces remote-default
discovery with `origin/v3`.

Discord composition and GitHub publication remain nullable and are supplied by
portable pack composition. This city configures no external publication edge,
so any imported Discord processes remain supervisor-internal and the pinned
pack is used gateway-only without patching its service definitions. The
stopped operator helper passes non-empty guild,
channel, and dedicated operator-role allowlists to the official
`gc discord import-app` command, then binds explicit operator DMs with
`gc discord bind-dm`. Public Interactions and `sync-commands` remain off by
omission; no local Discord daemon or service fork is needed. The Copilot
provider contract is complete without adding a separate lifecycle service.
