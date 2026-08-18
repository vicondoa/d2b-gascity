# Operator proxy example

This directory documents the deployment-only Nginx/TinyAuth relay. It is not
a Gas City lifecycle owner and it does not install or run a dashboard. The
dashboard is the SPA embedded in `gc supervisor`.

The example uses only generic values:

- dashboard host: `gascity.example.test`;
- auth host: `auth.gascity.example.test`;
- relay address: `192.0.2.10` from RFC 5737 documentation space;
- admitted external proxy CIDR: `192.0.2.0/24`;
- dashboard listener: `8373`;
- auth listener: `8374`;
- loopback TinyAuth: `127.0.0.1:8375`;
- loopback supervisor: `127.0.0.1:8372`.

Replace the documentation-space address and CIDR with host-local values
outside Git. Keep the auth host a subdomain of the dashboard host so the
TinyAuth parent-domain cookie covers both authorities.

## Boundary

The external OpenResty/TLS host forwards:

```text
https://gascity.example.test       -> http://192.0.2.10:8373
https://auth.gascity.example.test  -> http://192.0.2.10:8374
```

The private hop is source filtered. It is plain HTTP by design and does not
use mTLS. TLS termination, certificate files, and the source firewall remain
host-local deployment inputs. The residual interception risk on a
misconfigured private network is documented in
[`docs/dashboard-proxy.md`](../../docs/dashboard-proxy.md).

The same-host relay uses TinyAuth `5.1.3` and Nginx `1.30.4`. The module
renders the equivalent config from pinned package inputs; this file is a
generic reviewable template, not a place for real addresses, users, hashes,
or secrets.

The auth hostname must be exactly one label below the dashboard hostname.
The rewrite-phase `geo` source admission runs before Host handling, while
the listener `allow`/`deny` rules remain as defense in depth. Unsafe auth
mutations use the production Origin/Referer guard. Unknown nonempty auth
`Origin` values fail closed; only the exact auth origin and an empty origin
pass that map. Unsafe dashboard
mutations retain the native `X-GC-Request` requirement in Gas City.

## Install and validate

1. Supply a root-owned TinyAuth users file containing approved salted bcrypt
   hashes through the host credential mechanism.
2. Configure the external dashboard and auth authorities and the trusted
   proxy CIDR in host-local NixOS configuration.
3. Render or adapt `nginx.conf.example` without changing the fixed
   `127.0.0.1:8372` supervisor hop.
4. Validate the rendered file with `nginx -t`.
5. Check the dashboard deep link, login return URI, API, assets, health, SSE,
   logout, reauthentication, and a representative reversible control.

Never put password values, hashes, cookies, tokens, or private deployment
values in argv, logs, this example, or generated unit environment text.
Users and session/key rotation require a stopped TinyAuth restart according
to its supported lifecycle. The relay `Wants` TinyAuth and remains running
while TinyAuth is stopped, so `auth_request` fails closed; starting TinyAuth
again restores auth without a relay restart. Keep user-retained-state and
SQLite session-state rotation separate. Do not claim hot reload.

The complete contract, header rules, source admission, cookie scope, and
browser acceptance boundary are in
[`docs/dashboard-proxy.md`](../../docs/dashboard-proxy.md).
