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

`KillMode=control-group` makes the service cgroup the ownership boundary for
the supervisor and all of its upstream-managed children. The module does not
declare a Dolt unit, dashboard unit, controller unit, Discord unit, ACP unit,
or per-child lifecycle sidecar. Gas City starts and reconciles those children
itself. Bootstrap is an operator command, not `ExecStartPre`; an empty registry
is a valid service state.

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

The supervisor always binds to `127.0.0.1`. The port defaults to `8372` and
is an option value. Remote dashboard mode requires a host-supplied hostname,
which is emitted as the sole `allowed_hosts` entry. The generated file never
sets `allowed_origins`, `allow_mutations`, `write_auth_*`, or `read_auth_*`.
There is no non-loopback supervisor option.

Managed Dolt uses upstream dynamic allocation by default. A fixed
`dolt.fixedPort` is optional; when selected, it must be distinct from every
other listener and receives a matching Gas City owner rule. Dynamic Dolt
ports are never placed in the firewall.

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
not `PartOf` the Gas City service. They cannot launch or restart Gas City.
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
`Sec-Fetch-Site: same-origin`. Unsafe TinyAuth methods require the exact
`https://<authHostname>` Origin or a matching Referer. Missing native
`X-GC-Request` is passed through so Gas City can apply its own rejection.

Both relay listener ports are admitted only on the configured interface and
trusted external proxy CIDRs. A loopback owner policy permits the supervisor
port to be reached by the Gas City identity and relay identity only. TinyAuth's
raw loopback port accepts connections only from the relay identity. The
shared Gas City identity remains a deliberate trust boundary because upstream
children legitimately use the supervisor API.

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

Provider credentials, Discord composition, GitHub publication, and ACP
consumption remain nullable and are deferred to U5 and U6. This unit only
establishes safe credential projections and the lifecycle boundary.
