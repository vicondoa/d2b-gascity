# Embedded dashboard proxy contract

Gas City serves the only dashboard from the SPA embedded in `gc supervisor`.
This repository does not package a dashboard application, binary, unit, or
static dashboard service. The word "tinyproxy" in older operator notes means
the TinyAuth plus reverse-proxy path described here. It does not add the
Tinyproxy forward-proxy package.

## Required topology

```text
external TLS/OpenResty host
  https://gascity.example.test
    private HTTP, admitted source CIDR only
      same-host Nginx dashboard listener
        auth_request -> same-host TinyAuth auth listener
        proxy_pass  -> 127.0.0.1:8372

external TLS/OpenResty host
  https://auth.gascity.example.test
    private HTTP, admitted source CIDR only
      same-host Nginx auth listener
        proxy_pass  -> 127.0.0.1:8375
```

The dashboard listener is the only listener that forwards to Gas City. The
auth listener exposes TinyAuth root-relative login, logout, asset, and API
routes. `auth.gascity.example.test` is exactly one label below
`gascity.example.test`, so TinyAuth can issue one parent-domain cookie that
the browser sends to both listeners. Deeper names such as
`auth.ops.gascity.example.test` are invalid module configuration.

The supervisor bind and port are fixed. The generated supervisor file is
equivalent to:

```toml
[supervisor]
bind = "127.0.0.1"
port = 8372
allowed_hosts = ["gascity.example.test"]
```

The hostname is supplied by host-local NixOS configuration. The target file
does not set `allowed_origins`, `allow_mutations`, `write_auth_*`, or
`read_auth_*`. The loopback bind keeps the embedded first-party SPA
mutation-capable without enabling a grant-auth override.

## Header and request fidelity

The dashboard listener proxies the complete supervisor listener, not a
short allowlist of dashboard paths. It preserves:

- the browser `Host` and same-origin `Origin`;
- `Sec-Fetch-Site` and the native `X-GC-Request`;
- methods, request bodies, content headers, and cookies;
- event-stream responses and `Last-Event-ID` reconnect cursors.

The relay overwrites forwarded identity metadata with its own transport
values. Gas City authorization never trusts a client-supplied
`X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Port`, or
`X-Forwarded-Proto`. A forged forwarded header therefore cannot change the
Host, origin, CSRF, or mutation decision.

TinyAuth `auth_request` runs before every dashboard listener request,
including health, API, assets, deep links, and SSE. An unauthenticated
dashboard request receives a login redirect and never reaches `127.0.0.1:8372`.
The source admission rule is evaluated in the Nginx rewrite phase before each
Host check on both private listeners, and the `allow`/`deny` rules remain as
access-phase defense in depth.

## Pins and credential handling

The standalone source manifest pins TinyAuth `5.1.3` and Nginx `1.30.2`.
Only host-local configuration supplies the public authorities, private relay
address, trusted proxy CIDRs, users file, and authentication state. Do not
put those values in this repository.

TinyAuth uses approved salted bcrypt hashes from its host-local users
credential. Cookies are `Secure`, `HttpOnly`, `SameSite=Lax`, parent-domain
scoped, and bounded by both idle and absolute lifetimes. Production defaults
are one hour idle and one day absolute; the fixture uses shorter values only
to make expiry deterministic.

Login attempts are rate limited at the relay at five requests per minute with
a bounded burst, and TinyAuth also enforces three retries with a five-minute
login timeout. Logout is explicit. User material and session state rotation is
a stopped-service operation: replace the projected users credential, rotate
the session state according to the TinyAuth deployment procedure, and restart
TinyAuth. The relay only `Wants` TinyAuth and orders after it, so stopping
TinyAuth leaves the relay running but its `auth_request` path fails closed.
Starting TinyAuth again restores authenticated traffic without restarting the
relay. User-retained-state rotation and SQLite session-state rotation remain
separate operations. The fixture does not claim hot reload.

Passwords, hashes, cookies, and other auth material must not appear in
service arguments, generated unit environments, access logs, error logs, or
committed files. The NixOS module projects the users file with systemd
credentials rather than serializing its contents.

## Private HTTP boundary

The external TLS/OpenResty host terminates TLS and is the only admitted
source for the private HTTP listeners. The NixOS firewall and relay
`allow`/`deny` rules must agree on that source CIDR. No mTLS is used on the
private hop. The accepted residual risk is interception or spoofing on a
misconfigured private network; source filtering and the relay-side
`auth_request` remain mandatory. A deployment that needs a public supervisor
bind or stronger backend identity requires a separate design.

## Verification

`tests/fixtures/ingress/run.py` exercises the exact pinned runtime, a local
TLS frontend standing in for OpenResty, and the split listeners. It covers
HTTPS deep-link return metadata, parent-domain cookies, SPA `/api` and `/v0`
routes, assets and health, SSE and reconnect cursors, reversible mutation,
wrong-Host and forged-forwarded negatives, source admission before Host
handling, auth Origin/Referer guards, logout and reauthentication, separate
idle and absolute expiry, stopped user and session-state rotation, login
throttling, bounded write/read grant-auth negatives, supervisor outage and
recovery, secret redaction, and repeatable cleanup.

The fixture captures a real pre-restart supervisor SSE event id, reloads the
SPA from the authoritative dashboard route after restart, reconnects with
`Last-Event-ID`, and reads a later event after a post-restart health request.
It proves cursor advancement and fresh delivery supported by the pinned API;
it does not claim historical replay beyond that API behavior. The helper SSE
endpoint separately proves exact `Last-Event-ID` header fidelity and disabled
buffering.

No browser or Playwright dependency is added for the hermetic fixture. It
runs a static accessibility heuristic over the login and embedded dashboard
shells and bundles. U12 remains the real-browser requirement for keyboard and
screen-reader acceptance.
