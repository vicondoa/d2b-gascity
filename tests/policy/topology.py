from __future__ import annotations

import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
DASHBOARD_HOST = "gascity.example.test"
AUTH_HOST = "auth.gascity.example.test"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def tracked_paths(*prefixes: str) -> list[pathlib.Path]:
    output = subprocess.run(
        ["git", "ls-files", "--", *prefixes],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in output.stdout.splitlines() if line]


class DashboardTopologyTests(unittest.TestCase):
    def test_dashboard_is_embedded_and_has_no_standalone_owner(self) -> None:
        package = read("nix/packages/contributor.nix")
        module = read("nixos-modules/default.nix") + read("nixos-modules/ingress-relay.nix")
        smoke = read("tests/smoke/package.nix")

        self.assertNotIn("gascity-dashboard", package)
        self.assertNotRegex(module, r"(?i)systemd\.services\.[^\n]*dashboard")
        self.assertNotRegex(module, r"(?i)dashboard[^\n]*(?:package|binary|application|unit)")
        self.assertNotIn("tinyproxy", package.lower())
        self.assertIn("test ! -e", smoke)

        for path in tracked_paths("nix", "nixos-modules", "operator", "city"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(
                text,
                r"(?i)(?:gascity-dashboard|dashboard\.service|dashboard\.socket)",
                path.relative_to(ROOT).as_posix(),
            )

    def test_supervisor_is_fixed_loopback_and_forbidden_overrides_are_absent(self) -> None:
        module = (
            read("nixos-modules/options.nix")
            + read("nixos-modules/default.nix")
            + read("nixos-modules/ingress-relay.nix")
        )
        fixture = read("tests/fixtures/ingress/run.py")
        supervisor_config = read("tests/nix/module.nix")

        self.assertIn('bind = "127.0.0.1"', module)
        self.assertIn("supervisorPort = 8372", module)
        self.assertIn("port = ${toString supervisorPort}", module)
        self.assertIn("proxy_pass http://127.0.0.1:8372;", module)
        self.assertIn("SUPERVISOR_PORT = 8372", fixture)
        self.assertIn('bind = "127.0.0.1"', fixture)
        self.assertIn("port = {SUPERVISOR_PORT}", fixture)
        self.assertNotIn("supervisor.port", module)
        self.assertNotIn("supervisor.port", supervisor_config)
        self.assertNotRegex(module, r'(?m)\b(?:bind|listen)\s*=\s*["\'](?:0\.0\.0\.0|::)')
        self.assertNotRegex(fixture, r'(?m)\b(?:bind|listen)\s*=\s*["\'](?:0\.0\.0\.0|::)')
        self.assertIn("exactly one additional label", module)
        for forbidden in ("allowed_origins", "allow_mutations", "write_auth_", "read_auth_"):
            self.assertNotIn(forbidden, read("nixos-modules/default.nix"))
        self.assertIn("forbidden not in config_text", fixture)

    def test_firewall_owns_only_the_gas_city_nft_table(self) -> None:
        module = read("nixos-modules/default.nix")

        self.assertNotIn("networking.nftables.enable", module)
        self.assertNotIn("networking.nftables.ruleset", module)
        self.assertIn("config.networking.firewall.enable", module)
        self.assertIn('config.networking.firewall.backend == "iptables"', module)
        self.assertIn("networking.firewall.extraCommands", module)
        self.assertNotIn("networking.firewall.extraStopCommands", module)
        self.assertIn("${pkgs.nftables}/bin/nft", module)
        self.assertIn("destroy table inet d2b_gascity", module)
        self.assertEqual(module.count("${nftBinary} -f -"), 1)
        self.assertIn("chain input {", module)
        self.assertIn("chain output {", module)
        self.assertIn("type filter hook input priority 0; policy accept;", module)
        self.assertIn("type filter hook output priority 0; policy accept;", module)
        self.assertNotIn("flush ruleset", module.lower())
        self.assertNotRegex(
            module,
            r"delete\s+table\s+(?:ip|ip6|inet|bridge)(?!\s+d2b_gascity\b)",
        )
        self.assertNotIn("delete table", module)

    def test_split_hosts_and_complete_auth_request_listener_are_explicit(self) -> None:
        module = read("nixos-modules/ingress-relay.nix")
        fixture = read("tests/fixtures/ingress/nginx.conf.in")
        example = read("operator/proxy/nginx.conf.example")
        docs = read("docs/dashboard-proxy.md")

        for text in (fixture, example, docs):
            self.assertIn(DASHBOARD_HOST, text)
            self.assertIn(AUTH_HOST, text)

        self.assertIn("server_name ${remote.authHostname}", module)
        self.assertIn("server_name ${remote.hostname}", module)
        self.assertIn("auth_request /_d2b_tinyauth", module)
        self.assertIn("proxy_pass http://127.0.0.1:8372;", module)
        self.assertIn("auth_request /_gascity_tinyauth", example)
        self.assertGreaterEqual(fixture.count("server_name auth.gascity.example.test"), 1)
        self.assertGreaterEqual(fixture.count("server_name gascity.example.test"), 1)
        self.assertIn("allow 127.0.0.2;", fixture)
        self.assertIn("deny all;", fixture)
        self.assertIn("deny all;", module)
        self.assertIn("ssl_certificate @CERT@;", fixture)
        self.assertIn("proxy_bind 127.0.0.2;", fixture)
        self.assertIn("proxy_pass http://127.0.0.1:__RELAY_PORT__;", fixture)
        self.assertIn("proxy_pass http://127.0.0.1:__AUTH_PORT__;", fixture)
        self.assertIn("geo $fixture_source_admitted", fixture)
        self.assertIn("geo $d2b_source_admitted", module)
        self.assertIn("geo $gc_source_admitted", example)

    def test_browser_headers_methods_bodies_and_streams_survive_relay(self) -> None:
        surfaces = (
            read("nixos-modules/ingress-relay.nix"),
            read("tests/fixtures/ingress/nginx.conf.in"),
            read("operator/proxy/nginx.conf.example"),
        )
        required = (
            "proxy_set_header Host $http_host",
            "proxy_set_header Origin $http_origin",
            "proxy_set_header Referer $http_referer",
            "proxy_set_header Sec-Fetch-Site $http_sec_fetch_site",
            "proxy_set_header X-GC-Request $http_x_gc_request",
            "proxy_set_header Last-Event-ID $http_last_event_id",
            "proxy_set_header Cookie $http_cookie",
            "proxy_pass_request_body on",
            "proxy_buffering off",
            "proxy_request_buffering off",
        )
        for text in surfaces:
            for needle in required:
                self.assertIn(needle, text, needle)

        for forwarded_header in (
            "X-Forwarded-For",
            "X-Forwarded-Host",
            "X-Forwarded-Port",
            "X-Forwarded-Proto",
        ):
            self.assertIn(forwarded_header, read("docs/dashboard-proxy.md"))
        for path in tracked_paths("nixos-modules", "tests/fixtures/ingress", "operator/proxy"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(
                text,
                r"(?i)if\s*\(\s*\$http_x_forwarded|auth_request[^\n]*x-forwarded",
                path.relative_to(ROOT).as_posix(),
            )
        self.assertIn("auth_bad_origin", read("nixos-modules/ingress-relay.nix"))
        self.assertIn("auth_bad_referer", read("tests/fixtures/ingress/nginx.conf.in"))
        self.assertIn("gc_auth_bad_origin", read("operator/proxy/nginx.conf.example"))

    def test_auth_origin_maps_fail_closed_for_unknown_nonempty_origins(self) -> None:
        surfaces = (
            (
                "tests/fixtures/ingress/nginx.conf.in",
                "fixture_auth_bad_origin",
            ),
            (
                "operator/proxy/nginx.conf.example",
                "gc_auth_bad_origin",
            ),
        )
        for relative, variable in surfaces:
            text = read(relative)
            match = re.search(
                rf"map \$http_origin \${variable} \{{(?P<body>.*?)\n\s*\}}",
                text,
                re.DOTALL,
            )
            self.assertIsNotNone(match, relative)
            body = match.group("body")
            self.assertRegex(body, r"(?m)^\s*default 1;\s*$")
            self.assertRegex(body, r'(?m)^\s*"" 0;\s*$')
            self.assertIn(f'"https://{AUTH_HOST}" 0;', body)
            self.assertNotRegex(body, r"(?m)^\s*default 0;\s*$")

        module = read("nixos-modules/ingress-relay.nix")
        module_map = re.search(
            r"map \$http_origin \$d2b_auth_bad_origin \{(?P<body>.*?)\n\s*\}",
            module,
            re.DOTALL,
        )
        self.assertIsNotNone(module_map)
        self.assertRegex(module_map.group("body"), r"(?m)^\s*default 1;\s*$")
        self.assertRegex(module_map.group("body"), r'(?m)^\s*"" 0;\s*$')

    def test_tinyauth_stop_does_not_own_relay_lifecycle(self) -> None:
        module = read("nixos-modules/ingress-relay.nix")
        self.assertIn(
            'wants = [ "d2b-gascity-tinyauth.service" ];',
            module,
        )
        self.assertIn(
            'after = [ "d2b-gascity-tinyauth.service" ];',
            module,
        )
        self.assertNotIn(
            'requires = [ "d2b-gascity-tinyauth.service" ];',
            module,
        )

    def test_exact_ingress_pins_and_auth_hardening_are_present(self) -> None:
        flake = read("flake.nix")
        smoke = read("tests/smoke/package.nix")
        module = read("nixos-modules/ingress-relay.nix")
        fixture = read("tests/fixtures/ingress/run.py")
        docs = read("docs/dashboard-proxy.md")

        self.assertIn("nginx-1.30.2.tar.gz", flake)
        self.assertIn('expectedTinyAuthVersion="5.1.3"', smoke)
        self.assertIn('expectedNginxVersion="1.30.2"', smoke)
        for needle in (
            "securecookie: true",
            "subdomainsenabled: true",
            "sessionexpiry:",
            "sessionmaxlifetime:",
            "loginmaxretries:",
            "logintimeout:",
            "limit_req_zone",
            "limit_req_status 429",
        ):
            self.assertIn(needle, module + fixture)
        self.assertIn('DASHBOARD_URL = f"https://{DASHBOARD_HOST}"', fixture)
        self.assertIn('AUTH_URL = f"https://{AUTH_HOST}"', fixture)
        self.assertIn("CookieJar", fixture)
        self.assertIn("write_auth_verify_key", fixture)
        self.assertIn("read_auth_verify_key", fixture)
        self.assertIn("/api/health", fixture)
        self.assertIn("D2B_INGRESS_NETNS_INNER", fixture)
        self.assertIn("--map-root-user", fixture)
        self.assertIn('"link", "set", "lo", "up"', fixture)
        self.assertIn("wait_port_closed(SUPERVISOR_PORT)", fixture)
        self.assertIn("supervisor.poll()", fixture)
        self.assertIn("issued_cookie_values", fixture)
        self.assertIn("shutil.rmtree(base)", fixture)
        for needle in ("logout", "rotation", "Secure", "HttpOnly", "SameSite", "bcrypt"):
            self.assertIn(needle.lower(), docs.lower())
        self.assertNotIn("--auth.users=", module)
        self.assertNotIn("TINYAUTH_AUTH_USERS=", module)
        self.assertNotIn("proxy_set_header Authorization $http_authorization", module)

    def test_operator_example_has_no_private_values_or_tinyproxy_dependency(self) -> None:
        example = read("operator/proxy/nginx.conf.example")
        readme = read("operator/proxy/README.md")
        self.assertIn("192.0.2.10", example)
        self.assertIn("192.0.2.0/24", example)
        self.assertNotRegex(example + readme, r"(?i)(?:/etc/(?:ssl|gascity)/[^\s]+|password\s*[:=]|hash\s*[:=])")
        self.assertNotIn("tinyproxy", (example + readme).lower())
        self.assertIn("nginx -t", readme)
        self.assertIn("127.0.0.1:8372", example)
        self.assertIn("if ($gc_source_admitted = 0) { return 403; }", example)

    def test_accessibility_and_live_browser_boundary_are_documented(self) -> None:
        fixture = read("tests/fixtures/ingress/run.py")
        docs = read("docs/dashboard-proxy.md")
        self.assertIn("assert_static_accessibility_heuristic", fixture)
        self.assertIn("static accessibility heuristic", fixture)
        self.assertIn("U12 real-browser", fixture)
        self.assertNotIn("PASS keyboard", fixture)
        self.assertNotIn("PASS screen-reader", fixture)
        self.assertIn("U12", docs)
        self.assertIn("real-browser requirement", docs)


if __name__ == "__main__":
    unittest.main()
