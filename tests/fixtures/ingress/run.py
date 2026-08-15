#!/usr/bin/env python3
"""Credential-free U14 ingress proof for the embedded Gas City dashboard."""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


HOST = "gascity.example.test"
ORIGIN = f"http://{HOST}"
BUILD_ID = "f6741d94861aa14f0253deffbe9efb1cb3a35d92"
TINYAUTH_VERSION = "5.1.3"
NGINX_VERSION = "1.30.2"
FAKE_USER = "fixture"
FAKE_PASSWORD = "fixture-pass"


class Failure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_capture(args: list[str], env: dict[str, str], timeout: float = 30.0) -> tuple[int, str]:
    result = subprocess.run(args, cwd=env.get("D2B_INGRESS_WORKDIR"), env=env, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout + result.stderr


def wait_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise Failure(f"loopback port {port} did not open")


def request(
    port: int,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 5.0,
) -> tuple[int | None, dict[str, str], list[tuple[str, str]], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        pairs = response.getheaders()
        return response.status, {key.lower(): value for key, value in pairs}, pairs, response.read()
    except (OSError, http.client.HTTPException, TimeoutError):
        return None, {}, [], b""
    finally:
        connection.close()


def open_stream(
    port: int,
    path: str,
    headers: dict[str, str],
    timeout: float = 5.0,
) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    connection.request("GET", path, headers=headers)
    return connection, connection.getresponse()


def proc_snapshot(base: Path, roots: set[int]) -> dict[int, tuple[int, int, str]]:
    entries: dict[int, tuple[int, int, str]] = {}
    for item in Path("/proc").iterdir():
        if not item.name.isdigit():
            continue
        pid = int(item.name)
        try:
            raw_stat = (item / "stat").read_text()
            fields = raw_stat.rsplit(")", 1)[1].split()
            ppid, pgid = int(fields[1]), int(fields[2])
            command = (item / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            entries[pid] = (ppid, pgid, command)
        except (FileNotFoundError, PermissionError, ValueError, IndexError):
            continue
    selected = {pid for pid in roots if pid in entries}
    changed = True
    while changed:
        changed = False
        for pid, (ppid, _, command) in entries.items():
            if pid in selected:
                continue
            if ppid in selected or str(base) in command:
                selected.add(pid)
                changed = True
    return {pid: entries[pid] for pid in selected if pid in entries}


def owned_groups(base: Path, roots: set[int]) -> set[int]:
    groups = {pgid for _, (_, pgid, _) in proc_snapshot(base, roots).items()}
    groups.discard(os.getpgrp())
    return {group for group in groups if group > 1}


def signal_groups(groups: set[int], signum: int) -> None:
    for group in sorted(groups):
        try:
            os.killpg(group, signum)
        except ProcessLookupError:
            pass
        except PermissionError as error:
            raise Failure(f"cannot signal owned process group {group}: {error}") from error


def wait_groups_gone(base: Path, roots: set[int], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not proc_snapshot(base, roots):
            return True
        time.sleep(0.1)
    return not proc_snapshot(base, roots)


class FixtureStreamHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/fixture-sse":
            self.send_error(404)
            return
        cursor = self.headers.get("Last-Event-ID", "")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.wfile.write(f"id: {cursor}\ndata: first\n\n".encode())
        self.wfile.flush()
        time.sleep(0.8)
        self.wfile.write(b"data: second\n\n")
        self.wfile.flush()

    def log_message(self, _format: str, *_args: object) -> None:
        return


def nginx_config(path: Path, relay_port: int, supervisor_port: int, tinyauth_port: int, helper_port: int, base: Path) -> None:
    template = Path(__file__).with_name("nginx.conf.in").read_text(encoding="utf-8")
    replacements = (("@BASE@", base), ("@RELAY_PORT@", relay_port), ("@SUPERVISOR_PORT@", supervisor_port),
                    ("@TINYAUTH_PORT@", tinyauth_port), ("@HELPER_PORT@", helper_port))
    for marker, value in replacements:
        template = template.replace(marker, str(value))
    path.write_text(template, encoding="utf-8")


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    runtime_value = os.environ.get("D2B_INGRESS_RUNTIME", str(repo / ".scratch" / "ingress-runtime"))
    runtime = Path(runtime_value).expanduser().resolve()
    required_bins = ["gc", "dolt", "tinyauth", "nginx"]
    require(runtime.is_dir(), f"runtime not found: {runtime_value}")
    for name in required_bins:
        require((runtime / "bin" / name).is_file(), f"runtime is missing {name}")

    scratch_root = repo / ".scratch" / "ingress-runs"
    scratch_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    scratch_root.chmod(0o700)
    base = scratch_root / f"run-{os.getpid()}-{time.time_ns()}"
    base.mkdir(mode=0o700)
    processes: list[subprocess.Popen[bytes]] = []
    logs: list[object] = []
    helper: ThreadingHTTPServer | None = None
    supervisor_port = free_port()
    relay_port = free_port()
    tinyauth_port = free_port()
    helper_port = free_port()
    env = os.environ.copy()
    env.update(
        {
            "D2B_INGRESS_WORKDIR": str(base),
            "GC_HOME": str(base / "gc"),
            "XDG_CONFIG_HOME": str(base / "xdg-config"),
            "XDG_STATE_HOME": str(base / "xdg-state"),
            "XDG_DATA_HOME": str(base / "xdg-data"),
            "XDG_RUNTIME_DIR": str(base / "runtime"),
            "DOLT_ROOT_PATH": str(base / "dolt-root"),
            "GIT_CONFIG_GLOBAL": str(base / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "BD_NON_INTERACTIVE": "1",
            "NO_COLOR": "1",
            "GC_SUPERVISOR_LOG_TEE": "0",
        }
    )
    for directory in ("gc", "runtime", "xdg-config", "xdg-state", "xdg-data", "dolt-root"):
        (base / directory).mkdir(parents=True, exist_ok=True)
    (base / "nginx").mkdir(parents=True, exist_ok=True)
    (base / "gitconfig").write_text("[user]\n\tname = fixture\n\temail = fixture@example.test\n", encoding="utf-8")
    for key, value in (("user.name", FAKE_USER), ("user.email", "fixture@example.test")):
        code, _ = run_capture(
            [str(runtime / "bin" / "dolt"), "config", "--global", "--add", key, value],
            env,
        )
        require(code == 0, f"could not create private Dolt identity for {key}")

    def spawn(args: list[str], log_name: str) -> subprocess.Popen[bytes]:
        log = (base / log_name).open("wb")
        logs.append(log)
        process = subprocess.Popen(
            args,
            cwd=base,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        processes.append(process)
        return process

    def direct(path: str, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None):
        return request(supervisor_port, method, path, {"Host": HOST, **(headers or {})}, body)

    def relay(path: str, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None):
        return request(relay_port, method, path, {"Host": HOST, **(headers or {})}, body)

    try:
        gc_init = [
            str(runtime / "bin" / "gc"),
            "init",
            "--template",
            "empty",
            "--no-start",
            "--skip-provider-readiness",
            "--yes",
            str(base / "city"),
        ]
        code, output = run_capture(gc_init, env, timeout=90)
        require(code == 0, f"gc init failed ({code})")
        require("Initialized bare city" in output, "gc init did not create the fixture city")
        tiny_code, tiny_version = run_capture([str(runtime / "bin" / "tinyauth"), "version"], env)
        nginx_code, nginx_version = run_capture([str(runtime / "bin" / "nginx"), "-v"], env)
        require(tiny_code == 0 and TINYAUTH_VERSION in tiny_version, "TinyAuth is not the U2 pin")
        require(nginx_code == 0 and NGINX_VERSION in nginx_version, "Nginx is not the U2 pin")
        (base / "gc" / "supervisor.toml").write_text(
            f'[supervisor]\nbind = "127.0.0.1"\nport = {supervisor_port}\nallowed_hosts = ["{HOST}"]\n',
            encoding="utf-8",
        )
        supervisor = spawn([str(runtime / "bin" / "gc"), "supervisor", "run"], "supervisor.log")
        wait_port(supervisor_port)
        status, _, _, body = direct("/health")
        require(status == 200, "supervisor health did not open")
        health = json.loads(body)
        require(health.get("build_id") == BUILD_ID, "supervisor build ID is not the U2 pin")
        code, _ = run_capture(
            [str(runtime / "bin" / "gc"), "start", str(base / "city"), "--json"],
            env,
            timeout=90,
        )
        require(code == 0, "supported gc start/register path failed")

        def city_ready() -> bool:
            status, _, _, body = direct("/health")
            if status != 200:
                return False
            try:
                value = json.loads(body)
            except json.JSONDecodeError:
                return False
            return value.get("cities_running") == 1 and value.get("startup", {}).get("ready") is True

        wait_until(city_ready, 90, "fixture city did not become ready")
        city_status, _, _, city_body = direct("/v0/city/city/status")
        require(city_status == 200 and b'"suspended":false' in city_body, "fixture city status is not readable")

        user_code, user_output = run_capture(
            [
                str(runtime / "bin" / "tinyauth"),
                "user",
                "create",
                "--docker",
                "--username",
                FAKE_USER,
                "--password",
                FAKE_PASSWORD,
            ],
            env,
        )
        require(user_code == 0, "TinyAuth fake user generation failed")
        match = re.search(r"^--auth\.users=(\S+)$", user_output, re.MULTILINE)
        require(match is not None, "TinyAuth did not return a fake user hash")
        (base / "users").write_text(match.group(1) + "\n", encoding="utf-8")
        (base / "tinyauth.yml").write_text(
            f"""appurl: {ORIGIN}
server:
  address: 127.0.0.1
  port: {tinyauth_port}
auth:
  usersfile: {base / "users"}
  securecookie: true
  sessionexpiry: 600
  sessionmaxlifetime: 1800
  loginmaxretries: 3
  trustedproxies: 127.0.0.1
database:
  driver: memory
analytics:
  enabled: false
log:
  level: warn
""",
            encoding="utf-8",
        )
        tinyauth = spawn(
            [str(runtime / "bin" / "tinyauth"), "--configfile", str(base / "tinyauth.yml")],
            "tinyauth.log",
        )
        wait_port(tinyauth_port)

        helper = ThreadingHTTPServer(("127.0.0.1", helper_port), FixtureStreamHandler)
        threading.Thread(target=helper.serve_forever, daemon=True).start()
        config_path = base / "nginx.conf"
        nginx_config(config_path, relay_port, supervisor_port, tinyauth_port, helper_port, base)
        test_code, test_output = run_capture(
            [str(runtime / "bin" / "nginx"), "-t", "-p", str(base / "nginx"), "-c", str(config_path)],
            env,
        )
        require(test_code == 0, f"nginx config test failed: {test_output[-400:]}")
        nginx = spawn(
            [
                str(runtime / "bin" / "nginx"),
                "-p",
                str(base / "nginx"),
                "-c",
                str(config_path),
                "-g",
                "daemon off;",
            ],
            "nginx.log",
        )
        wait_port(relay_port)

        deep_path = "/agents?tab=events&fixture=1"
        status, headers, _, _ = relay(deep_path)
        require(status == 302, "unauthenticated deep link did not redirect")
        location = headers.get("location", "")
        parsed_location = urlsplit(location)
        return_values = []
        for key in ("redirect", "redirect_uri", "return", "url"):
            return_values.extend(parse_qs(parsed_location.query, keep_blank_values=True).get(key, []))
        def same_return_uri(value: str) -> bool:
            candidate = urlsplit(unquote(value))
            candidate_path = candidate.path + (f"?{candidate.query}" if candidate.query else "")
            return candidate_path == deep_path

        require(
            any(same_return_uri(value) for value in return_values),
            f"TinyAuth redirect did not preserve the exact return path and query: {location}",
        )
        require(parsed_location.path == "/login", "deep link did not redirect to TinyAuth login")
        print("PASS unauthenticated deep link redirect and exact return URI")

        login_body = json.dumps({"username": FAKE_USER, "password": FAKE_PASSWORD}).encode()
        status, _, pairs, _ = relay(
            "/api/user/login",
            "POST",
            {"Content-Type": "application/json", "Accept": "application/json"},
            login_body,
        )
        cookie_headers = [value for key, value in pairs if key.lower() == "set-cookie"]
        require(status in (200, 204, 302) and cookie_headers, "TinyAuth login did not return a session cookie")
        set_cookie = cookie_headers[0]
        cookie = set_cookie.split(";", 1)[0]
        cookie_lower = set_cookie.lower()
        require("secure" in cookie_lower and "httponly" in cookie_lower, "session cookie is not Secure and HttpOnly")
        require("samesite=lax" in cookie_lower, "session cookie is not SameSite=Lax")
        auth_headers = {"Cookie": cookie, "Sec-Fetch-Site": "same-origin"}
        print("PASS TinyAuth fake login and Secure HttpOnly SameSite cookie")

        status, headers, _, body = relay("/", headers=auth_headers)
        require(status == 200 and b"<html" in body.lower(), "authenticated dashboard HTML did not load")
        asset_match = re.search(rb'(?:src|href)="(/assets/[^"]+)"', body)
        require(asset_match is not None, "embedded dashboard did not expose an asset")
        asset_path = asset_match.group(1).decode()
        asset_status, _, _, asset_body = relay(asset_path, headers=auth_headers)
        require(asset_status == 200 and asset_body, "authenticated dashboard asset did not load")
        health_status, _, _, _ = relay("/health", headers=auth_headers)
        api_status, _, _, _ = relay("/v0/city/city/status", headers=auth_headers)
        require(health_status == 200 and api_status == 200, "authenticated health or API read failed")
        print("PASS authenticated SPA, health, API read, and asset")

        stream_connection, stream_response = open_stream(
            relay_port,
            "/v0/events/stream",
            {"Host": HOST, **auth_headers, "Accept": "text/event-stream", "Last-Event-ID": "fixture-cursor"},
        )
        try:
            require(stream_response.status == 200, "supervisor SSE did not open through relay")
            stream_headers = {key.lower(): value for key, value in stream_response.getheaders()}
            require("text/event-stream" in stream_headers.get("content-type", ""), "SSE content type was lost")
            require("no-cache" in stream_headers.get("cache-control", ""), "SSE cache contract was lost")
        finally:
            stream_connection.close()
        helper_connection, helper_response = open_stream(
            relay_port,
            "/__fixture/sse",
            {"Host": HOST, **auth_headers, "Accept": "text/event-stream", "Last-Event-ID": "fixture-cursor"},
        )
        try:
            require(helper_response.status == 200, "relay SSE contract endpoint did not open")
            helper_headers = {key.lower(): value for key, value in helper_response.getheaders()}
            require(helper_headers.get("x-d2b-sse-buffering") == "off", "relay buffering header contract is missing")
            started = time.monotonic()
            first_line = helper_response.readline()
            require(time.monotonic() - started < 0.6, "SSE first event was buffered")
            require(first_line == b"id: fixture-cursor\n", "Last-Event-ID was not preserved by relay")
        finally:
            helper_connection.close()
        print("PASS supervisor SSE open, unbuffered relay stream, and Last-Event-ID forwarding")

        mutation_headers = {
            **auth_headers,
            "Content-Type": "application/json",
            "Origin": ORIGIN,
            "Sec-Fetch-Site": "same-origin",
        }
        mutation_body = b'{"suspended":true}'
        missing_status, _, _, _ = relay("/v0/city/city", "PATCH", mutation_headers, mutation_body)
        require(missing_status == 403, "mutation without X-GC-Request was accepted")
        wrong_origin = {**mutation_headers, "Origin": "http://wrong.example.test", "X-GC-Request": "fixture"}
        for unsafe_method in ("POST", "PUT", "PATCH", "DELETE"):
            wrong_origin_status, _, _, _ = relay(
                "/v0/city/city",
                unsafe_method,
                wrong_origin,
                mutation_body,
            )
            require(
                wrong_origin_status == 403,
                f"cross-origin {unsafe_method} mutation was accepted",
            )
        cross_site = {**mutation_headers, "Sec-Fetch-Site": "cross-site", "X-GC-Request": "fixture"}
        cross_site_status, _, _, _ = relay("/v0/city/city", "PATCH", cross_site, mutation_body)
        require(cross_site_status == 403, "cross-site mutation was accepted")
        allowed = {**mutation_headers, "X-GC-Request": "dashboard"}
        allowed_status, _, _, _ = relay("/v0/city/city", "PATCH", allowed, mutation_body)
        require(allowed_status == 200, "same-origin mutation with native request header failed")
        restore_body = b'{"suspended":false}'
        restore_status, _, _, _ = relay("/v0/city/city", "PATCH", allowed, restore_body)
        require(restore_status == 200, "fixture city restore mutation failed")
        print("PASS mutation CSRF/source-header rejection and reversible suspend/restore")

        wrong_host_status, _, _, _ = request(relay_port, "GET", "/health", {"Host": "wrong.example.test"})
        require(wrong_host_status == 421, "wrong Host was not rejected by relay")
        direct_wrong_status, _, _, _ = request(supervisor_port, "GET", "/health", {"Host": "wrong.example.test"})
        require(direct_wrong_status == 421, "wrong Host was not rejected by supervisor")
        forged = {
            **auth_headers,
            "X-Forwarded-Host": "wrong.example.test",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Port": "443",
            "X-Forwarded-For": "203.0.113.77",
        }
        forged_status, _, _, _ = relay("/health", headers=forged)
        direct_forged_status, _, _, _ = direct(
            "/health",
            headers={
                "X-Forwarded-Host": "wrong.example.test",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Port": "443",
                "X-Forwarded-For": "203.0.113.77",
            },
        )
        require(forged_status == 200 and direct_forged_status == 200, "forged X-Forwarded headers changed Host decisions")
        print("PASS wrong Host rejection and forged X-Forwarded-* neutrality")

        protected_groups = owned_groups(base, {tinyauth.pid, nginx.pid})
        supervisor_groups_before = owned_groups(base, {supervisor.pid}) - protected_groups
        signal_groups(supervisor_groups_before, signal.SIGTERM)
        supervisor.wait(timeout=10)
        unavailable = False
        for _ in range(30):
            unavailable_status, _, _, _ = relay("/health", headers=auth_headers)
            if unavailable_status in (502, 503, 504):
                unavailable = True
                break
            time.sleep(0.1)
        require(unavailable, "relay did not report temporary supervisor unavailability")
        supervisor = spawn([str(runtime / "bin" / "gc"), "supervisor", "run"], "supervisor-restart.log")
        wait_port(supervisor_port)
        wait_until(city_ready, 90, "authenticated reads did not recover after supervisor restart")
        recovered_status, _, _, _ = relay("/health", headers=auth_headers)
        require(recovered_status == 200, "relay health did not recover after supervisor restart")
        print("PASS supervisor restart, temporary unavailable state, and authenticated recovery")

        config_text = (base / "gc" / "supervisor.toml").read_text(encoding="utf-8")
        for forbidden in ("allowed_origins", "allow_mutations", "write_auth_", "read_auth_"):
            require(forbidden not in config_text, f"supervisor config unexpectedly contains {forbidden}")
        print("PASS loopback supervisor, one external Host, and absent grant/CORS overrides")
        print(f"PASS exact runtime pins: Gas City {BUILD_ID}, TinyAuth {TINYAUTH_VERSION}, Nginx {NGINX_VERSION}")
        print("PASS U14 ingress fixture")
        return 0
    except (Failure, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"FAIL U14 ingress fixture: {error}", file=sys.stderr)
        return 1
    finally:
        if helper is not None:
            helper.shutdown()
            helper.server_close()
        root_pids = {process.pid for process in processes}
        all_groups = owned_groups(base, root_pids)
        signal_groups(all_groups, signal.SIGTERM)
        if not wait_groups_gone(base, root_pids, 5):
            signal_groups(owned_groups(base, root_pids), signal.SIGKILL)
            wait_groups_gone(base, root_pids, 3)
        for process in processes:
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass
        for log in logs:
            log.close()
        leaked = proc_snapshot(base, set())
        if leaked:
            print(
                "FAIL process leak: " + ", ".join(str(pid) for pid in sorted(leaked)),
                file=sys.stderr,
            )
            return 1
        if not leaked:
            shutil.rmtree(base, ignore_errors=True)


def wait_until(predicate, timeout: float, label: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.25)
    raise Failure(label)


if __name__ == "__main__":
    raise SystemExit(main())
