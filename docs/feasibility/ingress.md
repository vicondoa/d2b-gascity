# Embedded dashboard ingress fixture

This fixture checks the final U8 topology for the dashboard embedded in
`gc supervisor`. It is not a dashboard package, a browser application, or a
production deployment module.

## Exact runtime and commands

The proof uses:

- Gas City build `f6741d94861aa14f0253deffbe9efb1cb3a35d92`;
- TinyAuth `5.1.3`;
- Nginx `1.30.2`;
- fixed supervisor listener `127.0.0.1:8372`.

From this repository:

```sh
nix build .#packages.x86_64-linux.gas-city-contributor
D2B_INGRESS_RUNTIME=./result python3 tests/fixtures/ingress/run.py
```

The fixture automatically re-executes itself with the packaged
`unshare --user --map-root-user --net` command. Inside that unprivileged
network namespace it runs `ip link set lo up`, proves that
`127.0.0.1:8372` is closed, starts the fixture supervisor, and verifies that
the listener returns the pinned build id. It never stops or touches a
supervisor in the host namespace. For repeatability, run the exact command
twice. The fixture creates its fake salted bcrypt users at runtime, keeps all
state below `.scratch`, and removes its private directory after checking owned
process groups. It does not read or write committed credentials, cookies, host
configuration, or private deployment values.

## Final topology

```text
https://gascity.example.test:443
https://auth.gascity.example.test:443
  one local TLS frontend standing in for external OpenResty
    private HTTP from 127.0.0.2, trusted source CIDR only
      split Nginx dashboard/auth listeners
        dashboard auth_request -> TinyAuth auth listener
        dashboard proxy_pass  -> 127.0.0.1:8372
        auth proxy_pass       -> 127.0.0.1:<fixture TinyAuth port>
```

The dashboard host is the only authority forwarded to the embedded
supervisor. The auth host is its subdomain so the Secure, HttpOnly,
SameSite=Lax cookie uses the parent `gascity.example.test` Domain. The
dashboard listener authenticates every route before forwarding. Its rewrite
phase source admission rejects direct 127.0.0.1 inner requests before Host
handling, and the retained allow/deny rules provide a second defense. Its
default server rejects unknown Host values.

The generated supervisor configuration is:

```toml
[supervisor]
bind = "127.0.0.1"
port = 8372
allowed_hosts = ["gascity.example.test"]
```

`allowed_origins`, `allow_mutations`, `write_auth_*`, and `read_auth_*` are
absent. The relay preserves the external Host, Origin, `Sec-Fetch-Site`,
native `X-GC-Request`, methods, bodies, cookies, SSE, and `Last-Event-ID`.
Forged `X-Forwarded-*` values are overwritten or ignored for Gas City
decisions.

## Covered journeys

The fixture proves:

1. exact split-host HTTPS deep-link login and return URI, including scheme,
   host, default port semantics, path, and query;
2. auth listener login, parent-domain cookie scope, Secure/HttpOnly/SameSite
   attributes, and bounded expiry;
3. embedded SPA HTML, an asset, health, API, and the complete listener path;
4. a real supervisor SSE cursor before restart, authoritative SPA reload,
   post-restart delivery after reconnecting with `Last-Event-ID`, and a
   separate unbuffered helper SSE header-fidelity proof;
5. missing native request header, wrong Origin, cross-site fetch, and
   reversible same-origin mutation negatives;
6. wrong Host and forged forwarded-header neutrality;
7. explicit logout, old-cookie denial, and reauthentication;
8. separate idle and active absolute session expiry;
9. stopped TinyAuth user rotation with retained state and observed existing
    cookie behavior, followed by separate stopped SQLite session-state
    rotation; each material or state change occurs only after the process and
    port are confirmed stopped;
10. bounded login rate limiting, wrong-password no-cookie failures, and
    absence of fake password/hash material in
    long-lived argv and logs;
11. bounded `write_auth_verify_key` and `read_auth_verify_key` negatives
     against grant-less first-party mutation/read requests while the target
     config remains grant-free;
12. supervisor outage, authoritative dashboard reload, real SSE reconnect,
     helper Last-Event-ID fidelity, and recovery without a second dashboard
     process;
13. static accessibility heuristic checks.

TinyAuth user and session rotation is deliberately a stopped-service
operation. The relay remains up and fails closed while TinyAuth is stopped,
then recovers when TinyAuth starts again. The fixture does not claim hot
reload or historical SSE replay beyond the pinned API's observed cursor
behavior. The static accessibility heuristic is used because no browser or
Playwright dependency is added; U12 remains the real-browser keyboard and
screen-reader requirement.

## Private HTTP residual risk

The real deployment must terminate TLS on the external OpenResty host and
allow only that source CIDR to reach the two private relay listeners. The
backend hop is plain HTTP and does not use mTLS. The residual risk is
interception or spoofing on a misconfigured private network. The relay-side
TinyAuth `auth_request`, source admission, fixed loopback final hop, and
supervisor Host/origin checks remain mandatory.

See [`docs/dashboard-proxy.md`](../dashboard-proxy.md) for the operator
contract and [`operator/proxy/README.md`](../../operator/proxy/README.md) for
the generic Nginx example.
