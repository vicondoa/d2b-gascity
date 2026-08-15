#!/usr/bin/env python3
"""Credential-free U8 ingress proof for the embedded Gas City dashboard."""

from __future__ import annotations

import base64
import http.cookiejar
import http.client
import json
import os
import re
import shutil
import signal
import ssl
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import (
    HTTPSHandler,
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    Request,
    build_opener,
)


DASHBOARD_HOST = "gascity.example.test"
AUTH_HOST = "auth.gascity.example.test"
DASHBOARD_URL = f"https://{DASHBOARD_HOST}"
AUTH_URL = f"https://{AUTH_HOST}"
ORIGIN = DASHBOARD_URL
AUTH_ORIGIN = AUTH_URL
SUPERVISOR_PORT = 8372
FIXTURE_SESSION_EXPIRY = 4
FIXTURE_SESSION_MAX_LIFETIME = 15
BUILD_ID = "f6741d94861aa14f0253deffbe9efb1cb3a35d92"
TINYAUTH_VERSION = "5.1.3"
NGINX_VERSION = "1.30.2"
FAKE_USER = "fixture"
FAKE_PASSWORD = "fixture-pass"
ROTATED_PASSWORD = "fixture-rotated-pass"
TLS_SOURCE_ADDRESS = "127.0.0.2"
NETNS_ENV = "D2B_INGRESS_NETNS_INNER"


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


def wait_port(port: int, address: str = "127.0.0.1", timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((address, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise Failure(f"loopback port {address}:{port} did not open")


def wait_port_closed(port: int, address: str = "127.0.0.1", timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((address, port), timeout=0.2):
                time.sleep(0.1)
        except OSError:
            return
    raise Failure(f"loopback port {address}:{port} did not close")


def request(
    address: str,
    port: int,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 5.0,
    source_address: str | None = None,
) -> tuple[int | None, dict[str, str], list[tuple[str, str]], bytes]:
    connection = http.client.HTTPConnection(
        address,
        port,
        timeout=timeout,
        source_address=(source_address, 0) if source_address else None,
    )
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
    address: str,
    port: int,
    path: str,
    headers: dict[str, str],
    timeout: float = 5.0,
) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse]:
    connection = http.client.HTTPConnection(address, port, timeout=timeout)
    connection.request("GET", path, headers=headers)
    return connection, connection.getresponse()


class LoopbackHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        tls_port: int,
        context: ssl.SSLContext,
        source_address: str,
        timeout: float | object = socket._GLOBAL_DEFAULT_TIMEOUT,
        **kwargs: object,
    ) -> None:
        super().__init__(host, port=tls_port, timeout=timeout, context=context, **kwargs)
        self.fixture_source_address = source_address
        self.fixture_tls_port = tls_port
        self.fixture_server_hostname = host

    def connect(self) -> None:
        self.sock = socket.create_connection(
            ("127.0.0.1", self.fixture_tls_port),
            self.timeout,
            source_address=(self.fixture_source_address, 0),
        )
        self.sock = self._context.wrap_socket(
            self.sock,
            server_hostname=self.fixture_server_hostname,
        )


class FixtureHTTPSHandler(HTTPSHandler):
    def __init__(
        self,
        tls_port: int,
        context: ssl.SSLContext,
        source_address: str,
    ) -> None:
        super().__init__(context=context)
        self.fixture_tls_port = tls_port
        self.fixture_source_address = source_address

    def https_open(self, request: Request):
        return self.do_open(
            lambda host, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, **kwargs: LoopbackHTTPSConnection(
                host,
                self.fixture_tls_port,
                self._context,
                self.fixture_source_address,
                timeout=timeout,
                **kwargs,
            ),
            request,
        )


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object):
        return None


class PublicCookieClient:
    instances: list["PublicCookieClient"] = []

    def __init__(
        self,
        tls_port: int,
        certificate: Path,
        source_address: str = "127.0.0.1",
    ) -> None:
        self.cookies = http.cookiejar.CookieJar()
        self.issued_cookie_values: set[str] = set()
        self.last_error: str | None = None
        self.__class__.instances.append(self)
        context = ssl.create_default_context(cafile=str(certificate))
        self.opener = build_opener(
            HTTPCookieProcessor(self.cookies),
            FixtureHTTPSHandler(tls_port, context, source_address),
            NoRedirectHandler(),
        )
        self.tls_port = tls_port
        self.context = context
        self.source_address = source_address

    def capture_cookie_headers(self, pairs: list[tuple[str, str]]) -> None:
        for key, value in pairs:
            if key.lower() != "set-cookie":
                continue
            cookie_pair = value.split(";", 1)[0]
            _, separator, cookie_value = cookie_pair.partition("=")
            if separator and cookie_value:
                self.issued_cookie_values.add(cookie_value)
        self.issued_cookie_values.update(cookie.value for cookie in self.cookies)

    def cookie_header(self, url: str) -> str:
        request = Request(url)
        self.cookies.add_cookie_header(request)
        return request.get_header("Cookie", "")

    def request(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> tuple[int | None, dict[str, str], list[tuple[str, str]], bytes]:
        self.last_error = None
        request = Request(url, data=body, headers=headers or {}, method=method)
        try:
            response = self.opener.open(request, timeout=5)
        except HTTPError as error:
            response = error
        except (OSError, ValueError, TimeoutError) as error:
            self.last_error = repr(error)
            return None, {}, [], b""
        try:
            pairs = response.getheaders()
            self.capture_cookie_headers(pairs)
            return response.status, {key.lower(): value for key, value in pairs}, pairs, response.read()
        finally:
            response.close()

    def open_stream(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> tuple[LoopbackHTTPSConnection, http.client.HTTPResponse]:
        parsed = urlsplit(url)
        require(parsed.scheme == "https" and parsed.hostname in (DASHBOARD_HOST, AUTH_HOST), "stream URL is not public HTTPS")
        request = Request(url, headers=headers or {}, method="GET")
        self.cookies.add_cookie_header(request)
        connection = LoopbackHTTPSConnection(
            parsed.hostname,
            self.tls_port,
            self.context,
            self.source_address,
            timeout=5,
        )
        connection.request(
            "GET",
            parsed.path + (f"?{parsed.query}" if parsed.query else ""),
            headers=dict(request.header_items()),
        )
        response = connection.getresponse()
        self.capture_cookie_headers(response.getheaders())
        return connection, response


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
        except (
            FileNotFoundError,
            PermissionError,
            ProcessLookupError,
            ValueError,
            IndexError,
        ):
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


def nginx_config(
    path: Path,
    relay_port: int,
    auth_port: int,
    supervisor_port: int,
    tinyauth_port: int,
    helper_port: int,
    tls_port: int,
    certificate: Path,
    key: Path,
    base: Path,
) -> None:
    template = Path(__file__).with_name("nginx.conf.in").read_text(encoding="utf-8")
    replacements = (
        ("@BASE@", base),
        ("__RELAY_PORT__", relay_port),
        ("__AUTH_PORT__", auth_port),
        ("__SUPERVISOR_PORT__", supervisor_port),
        ("__TINYAUTH_PORT__", tinyauth_port),
        ("__HELPER_PORT__", helper_port),
        ("__TLS_PORT__", tls_port),
        ("@CERT@", certificate),
        ("@KEY@", key),
    )
    for marker, value in replacements:
        template = template.replace(marker, str(value))
    path.write_text(template, encoding="utf-8")


def create_fixture_certificate(runtime: Path, base: Path, env: dict[str, str]) -> tuple[Path, Path]:
    openssl = runtime / "bin" / "openssl"
    if not openssl.is_file():
        discovered = shutil.which("openssl")
        require(discovered is not None, "fixture requires an available openssl command")
        openssl = Path(discovered)
    certificate = base / "fixture-cert.pem"
    key = base / "fixture-key.pem"
    code, output = run_capture(
        [
            str(openssl),
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-days",
            "1",
            "-subj",
            f"/CN={DASHBOARD_HOST}",
            "-addext",
            f"subjectAltName=DNS:{DASHBOARD_HOST},DNS:{AUTH_HOST}",
        ],
        env,
        timeout=30,
    )
    require(code == 0, f"fixture TLS certificate generation failed: {output[-400:]}")
    certificate.chmod(0o600)
    key.chmod(0o600)
    return certificate, key


def cookie_attributes(value: str) -> dict[str, str | None]:
    attributes: dict[str, str | None] = {}
    for part in value.split(";")[1:]:
        name, separator, attribute_value = part.strip().partition("=")
        attributes[name.lower()] = attribute_value if separator else None
    return attributes


def assert_static_accessibility_heuristic(
    login_body: bytes,
    login_asset_body: bytes,
    dashboard_body: bytes,
    asset_body: bytes,
) -> None:
    login_html = login_body.decode("utf-8", errors="replace").lower()
    login_asset_text = login_asset_body.decode("utf-8", errors="replace").lower()
    dashboard_html = dashboard_body.decode("utf-8", errors="replace").lower()
    asset_text = asset_body.decode("utf-8", errors="replace").lower()
    require("<title" in login_html and "<title" in dashboard_html, "embedded pages lack document titles")
    require(
        re.search(r'id=["\'](?:app|root)["\']|<main\b|role=["\']main["\']', login_html) is not None,
        "TinyAuth login shell lacks a mount point or main landmark",
    )
    require(
        re.search(r"<input\b|<button\b|aria-label", login_asset_text) is not None,
        "TinyAuth login bundle lacks a focusable control",
    )
    require(
        re.search(r"<label\b|aria-label|aria-labelledby", login_asset_text) is not None,
        "TinyAuth login bundle lacks labels",
    )
    require(
        re.search(r'id=["\'](?:app|root)["\']|<main\b|role=["\']main["\']', dashboard_html) is not None,
        "embedded dashboard lacks a mount point or main landmark",
    )
    require(
        re.search(r"<button\b|aria-label|role:", asset_text) is not None,
        "embedded dashboard bundle lacks recognizable accessible controls",
    )
    require(
        re.search(r"aria-label|aria-labelledby|<label\b", asset_text) is not None,
        "embedded dashboard bundle lacks labels",
    )
    require(
        re.search(r"<(?:button|a|input|select|textarea)[^>]*>\s*</(?:button|a)>", dashboard_html)
        is None,
        "embedded dashboard contains an obvious empty control",
    )


def reexec_in_network_namespace(repo: Path, runtime: Path) -> int:
    unshare = runtime / "bin" / "unshare"
    require(unshare.is_file(), f"runtime is missing unshare: {unshare}")
    inner_env = os.environ.copy()
    inner_env[NETNS_ENV] = "1"
    command = [
        str(unshare),
        "--user",
        "--map-root-user",
        "--net",
        sys.executable,
        str(Path(__file__).resolve()),
        *sys.argv[1:],
    ]
    return subprocess.run(command, cwd=repo, env=inner_env).returncode


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    runtime_value = os.environ.get("D2B_INGRESS_RUNTIME", str(repo / ".scratch" / "ingress-runtime"))
    runtime = Path(runtime_value).expanduser().resolve()
    required_bins = ["gc", "dolt", "tinyauth", "nginx", "unshare", "ip"]
    require(runtime.is_dir(), f"runtime not found: {runtime_value}")
    for name in required_bins:
        require((runtime / "bin" / name).is_file(), f"runtime is missing {name}")
    if os.environ.get(NETNS_ENV) != "1":
        return reexec_in_network_namespace(repo, runtime)

    namespace_env = os.environ.copy()
    namespace_env["HOME"] = "/root"
    os.environ["HOME"] = "/root"
    code, output = run_capture(
        [str(runtime / "bin" / "ip"), "link", "set", "lo", "up"],
        namespace_env,
        timeout=10,
    )
    require(code == 0, f"could not bring namespace loopback up: {output[-400:]}")
    wait_port_closed(SUPERVISOR_PORT)

    scratch_root = repo / ".scratch" / "ingress-runs"
    scratch_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    scratch_root.chmod(0o700)
    base = scratch_root / f"run-{os.getpid()}-{time.time_ns()}"
    base.mkdir(mode=0o700)
    processes: list[subprocess.Popen[bytes]] = []
    logs: list[object] = []
    helper: ThreadingHTTPServer | None = None
    supervisor_port = SUPERVISOR_PORT
    relay_port = free_port()
    auth_port = free_port()
    tinyauth_port = free_port()
    helper_port = free_port()
    tls_port = free_port()
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

    def stop_owned(process: subprocess.Popen[bytes]) -> None:
        try:
            process_group = os.getpgid(process.pid)
        except ProcessLookupError:
            process_group = None
        if process_group is not None:
            signal_groups({process_group}, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if process_group is not None:
                signal_groups({process_group}, signal.SIGKILL)
            process.wait(timeout=10)

    def create_user_hash(password: str) -> str:
        user_code, user_output = run_capture(
            [
                str(runtime / "bin" / "tinyauth"),
                "user",
                "create",
                "--docker",
                "--username",
                FAKE_USER,
                "--password",
                password,
            ],
            env,
        )
        require(user_code == 0, "TinyAuth fake user generation failed")
        match = re.search(r"^--auth\.users=(\S+)$", user_output, re.MULTILINE)
        require(match is not None, "TinyAuth did not return a fake user hash")
        user_hash = match.group(1)
        require(
            re.fullmatch(
                rf"{re.escape(FAKE_USER)}:\$2[aby]\$\d{{2}}\$[./A-Za-z0-9]{{53}}",
                user_hash,
            )
            is not None,
            "TinyAuth did not return an approved salted bcrypt hash",
        )
        return user_hash

    def direct(
        path: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ):
        return request(
            "127.0.0.1",
            supervisor_port,
            method,
            path,
            {"Host": DASHBOARD_HOST, **(headers or {})},
            body,
        )

    def inner_auth(
        path: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        address: str = "127.0.0.1",
        source_address: str | None = None,
    ):
        return request(
            address,
            auth_port,
            method,
            path,
            {"Host": AUTH_HOST, **(headers or {})},
            body,
            source_address=source_address,
        )

    def inner_relay(
        path: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        address: str = "127.0.0.1",
        source_address: str | None = None,
    ):
        return request(
            address,
            relay_port,
            method,
            path,
            {"Host": DASHBOARD_HOST, **(headers or {})},
            body,
            source_address=source_address,
        )

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
        require(code == 0, f"gc init failed ({code}): {output[-400:]}")
        require("Initialized bare city" in output, "gc init did not create the fixture city")
        tiny_code, tiny_version = run_capture([str(runtime / "bin" / "tinyauth"), "version"], env)
        nginx_code, nginx_version = run_capture([str(runtime / "bin" / "nginx"), "-v"], env)
        require(tiny_code == 0 and TINYAUTH_VERSION in tiny_version, "TinyAuth pin mismatch")
        require(nginx_code == 0 and NGINX_VERSION in nginx_version, "Nginx pin mismatch")
        supervisor_config_path = base / "gc" / "supervisor.toml"
        base_supervisor_config = (
            f'[supervisor]\nbind = "127.0.0.1"\nport = {SUPERVISOR_PORT}\n'
            f'allowed_hosts = ["{DASHBOARD_HOST}"]\n'
        )
        supervisor_config_path.write_text(base_supervisor_config, encoding="utf-8")
        supervisor = spawn([str(runtime / "bin" / "gc"), "supervisor", "run"], "supervisor.log")
        wait_port(supervisor_port)
        require(
            supervisor.poll() is None,
            "fixture supervisor exited while opening the fixed 8372 listener",
        )
        status, _, _, body = direct("/health")
        require(status == 200, "supervisor health did not open")
        health = json.loads(body)
        require(
            health.get("build_id") == BUILD_ID,
            "fixed 8372 listener is not the fixture supervisor build",
        )
        code, start_output = run_capture(
            [str(runtime / "bin" / "gc"), "start", str(base / "city"), "--json"],
            env,
            timeout=90,
        )
        require(
            code == 0,
            f"supported gc start/register path failed: {start_output[-400:]}",
        )

        def city_ready() -> bool:
            status, _, _, body = direct("/health")
            if status != 200:
                return False
            try:
                value = json.loads(body)
            except json.JSONDecodeError:
                return False
            return value.get("cities_running") == 1 and value.get("startup", {}).get("ready") is True

        def restart_supervisor(config_text: str, log_name: str) -> None:
            nonlocal supervisor
            stop_owned(supervisor)
            wait_port_closed(supervisor_port)
            supervisor_config_path.write_text(config_text, encoding="utf-8")
            supervisor = spawn(
                [str(runtime / "bin" / "gc"), "supervisor", "run"],
                log_name,
            )
            wait_port(supervisor_port)
            wait_until(city_ready, 90, "fixture city did not recover after supervisor restart")

        wait_until(city_ready, 90, "fixture city did not become ready")
        city_status, _, _, city_body = direct("/v0/city/city/status")
        require(city_status == 200 and b'"suspended":false' in city_body, "fixture city status is not readable")

        user_hash = create_user_hash(FAKE_PASSWORD)
        users_path = base / "users"
        users_path.write_text(user_hash + "\n", encoding="utf-8")
        users_path.chmod(0o600)
        (base / "tinyauth.yml").write_text(
            f"""appurl: {AUTH_ORIGIN}
server:
  address: 127.0.0.1
  port: {tinyauth_port}
auth:
  usersfile: {users_path}
  securecookie: true
  subdomainsenabled: true
  sessionexpiry: {FIXTURE_SESSION_EXPIRY}
  sessionmaxlifetime: {FIXTURE_SESSION_MAX_LIFETIME}
  loginmaxretries: 3
  logintimeout: 30
  trustedproxies: 127.0.0.0/8
database:
  driver: sqlite
  path: {base / "tinyauth.db"}
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
        certificate, key = create_fixture_certificate(runtime, base, env)
        config_path = base / "nginx.conf"
        nginx_config(
            config_path,
            relay_port,
            auth_port,
            supervisor_port,
            tinyauth_port,
            helper_port,
            tls_port,
            certificate,
            key,
            base,
        )
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
        wait_port(tls_port)
        wait_port(relay_port)
        wait_port(auth_port)
        require(nginx.poll() is None, "Nginx exited while opening fixture listeners")
        relay_pid = nginx.pid
        public_client = PublicCookieClient(tls_port, certificate)
        rate_client = PublicCookieClient(tls_port, certificate, source_address="127.0.0.3")

        deep_path = "/agents?tab=events&fixture=1"
        status, headers, _, _ = public_client.request(DASHBOARD_URL + deep_path)
        require(
            status == 302,
            "unauthenticated deep link did not redirect: "
            f"status={status}, headers={headers}, error={public_client.last_error}",
        )
        location = headers.get("location", "")
        parsed_location = urlsplit(location)
        return_values = []
        for key in ("redirect", "redirect_uri", "return", "url"):
            return_values.extend(parse_qs(parsed_location.query, keep_blank_values=True).get(key, []))

        def same_return_uri(value: str) -> bool:
            candidate = urlsplit(unquote(value))
            candidate_path = candidate.path + (f"?{candidate.query}" if candidate.query else "")
            return (
                candidate.scheme == "https"
                and candidate.hostname == DASHBOARD_HOST
                and candidate.port is None
                and candidate_path == deep_path
            )

        require(
            any(same_return_uri(value) for value in return_values),
            f"TinyAuth redirect did not preserve the exact HTTPS return URI: {location}",
        )
        require(parsed_location.scheme == "https", "TinyAuth login redirect did not use HTTPS")
        require(parsed_location.hostname == AUTH_HOST, "TinyAuth redirect did not use the split auth host")
        require(parsed_location.port is None, "TinyAuth redirect added a non-default auth port")
        require(parsed_location.path == "/login", "deep link did not redirect to TinyAuth login")
        login_status, _, _, login_html = public_client.request(location)
        require(login_status == 200 and b"<html" in login_html.lower(), "TinyAuth login page did not load over public HTTPS")

        direct_relay_status, _, _, _ = inner_relay(
            "/health",
            headers={"Host": "wrong.example.test"},
            address="127.0.0.1",
        )
        direct_auth_status, _, _, _ = inner_auth(
            "/login",
            headers={"Host": "wrong.example.test"},
            address="127.0.0.1",
        )
        require(
            direct_relay_status == 403 and direct_auth_status == 403,
            "unadmitted direct inner requests were not rejected before Host handling: "
            f"relay={direct_relay_status}, auth={direct_auth_status}",
        )
        admitted_wrong_auth_status, _, _, _ = inner_auth(
            "/login",
            headers={"Host": DASHBOARD_HOST},
            source_address=TLS_SOURCE_ADDRESS,
        )
        require(
            admitted_wrong_auth_status == 421,
            f"admitted wrong Host did not reach Host defense: status={admitted_wrong_auth_status}",
        )
        print("PASS HTTPS deep-link return URI, default-port metadata, and pre-Host source admission")

        def auth_mutation_headers() -> dict[str, str]:
            return {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": AUTH_ORIGIN,
                "Referer": AUTH_ORIGIN + "/login",
                "Sec-Fetch-Site": "same-origin",
            }

        def login(
            client: PublicCookieClient,
            password: str,
            username: str = FAKE_USER,
            require_cookie: bool = True,
        ) -> tuple[int | None, dict[str, str], list[tuple[str, str]], bytes]:
            body = json.dumps({"username": username, "password": password}).encode()
            response = client.request(
                AUTH_URL + "/api/user/login",
                "POST",
                auth_mutation_headers(),
                body,
            )
            status, response_headers, pairs, response_body = response
            if require_cookie and not (
                status in (200, 204, 302)
                and any(key.lower() == "set-cookie" for key, _ in pairs)
            ):
                raise Failure(
                    "TinyAuth login did not return a session cookie: "
                    f"status={status}, headers={sorted(response_headers)}, body={response_body[:160]!r}"
                )
            return response

        login_status, _, login_pairs, _ = login(public_client, FAKE_PASSWORD)
        login_cookie_headers = [
            value for key, value in login_pairs if key.lower() == "set-cookie"
        ]
        require(
            login_status in (200, 204, 302) and login_cookie_headers,
            "TinyAuth login did not return a session cookie",
        )
        set_cookie = login_cookie_headers[0]
        attributes = cookie_attributes(set_cookie)
        require("secure" in set_cookie.lower() and "httponly" in set_cookie.lower(), "session cookie is not Secure and HttpOnly")
        require("samesite=lax" in set_cookie.lower(), "session cookie is not SameSite=Lax")
        require(
            (attributes.get("domain") or "").lstrip(".") == DASHBOARD_HOST,
            "session cookie Domain does not cover both split hosts",
        )
        require(attributes.get("path") == "/", "session cookie Path is not root-scoped")
        require(attributes.get("expires") is not None, "session cookie lacks an expiry")
        require(
            attributes.get("max-age") is not None
            and int(attributes["max-age"] or "0") <= FIXTURE_SESSION_MAX_LIFETIME,
            "session cookie lifetime is not bounded",
        )
        dashboard_cookie = public_client.cookie_header(DASHBOARD_URL + "/health")
        auth_cookie = public_client.cookie_header(AUTH_URL + "/api/auth/nginx")
        require(dashboard_cookie and dashboard_cookie == auth_cookie, "parent-domain cookie was not selected for both HTTPS authorities")
        insecure_request = Request(f"http://{DASHBOARD_HOST}/health")
        public_client.cookies.add_cookie_header(insecure_request)
        require(not insecure_request.get_header("Cookie"), "Secure cookie was selected for an HTTP URL")
        auth_probe_status, _, _, _ = public_client.request(AUTH_URL + "/api/auth/nginx")
        require(auth_probe_status == 200, "parent-domain cookie was not accepted by the auth authority")
        print("PASS TinyAuth login, Secure HttpOnly SameSite cookie, and parent-domain selection")

        deep_status, _, _, deep_body = public_client.request(
            DASHBOARD_URL + deep_path,
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        require(
            deep_status == 200 and b"<html" in deep_body.lower(),
            "authenticated deep link did not load through the CookieJar",
        )
        print(f"PASS authenticated deep link preserved: {deep_path}")

        dashboard_status, _, _, dashboard_body = public_client.request(
            DASHBOARD_URL + "/",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        require(dashboard_status == 200 and b"<html" in dashboard_body.lower(), "authenticated dashboard HTML did not load")
        asset_match = re.search(rb'(?:src|href)="(/assets/[^"]+)"', dashboard_body)
        require(asset_match is not None, "embedded dashboard did not expose an asset")
        asset_path = asset_match.group(1).decode()
        asset_status, _, _, asset_body = public_client.request(
            DASHBOARD_URL + asset_path,
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        require(asset_status == 200 and asset_body, "authenticated dashboard asset did not load")
        health_status, _, _, _ = public_client.request(
            DASHBOARD_URL + "/health",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        v0_status, _, _, _ = public_client.request(
            DASHBOARD_URL + "/v0/city/city/status",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        api_status, api_headers, _, api_body = public_client.request(
            DASHBOARD_URL + "/api/health",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        require(health_status == 200 and v0_status == 200, "authenticated health or /v0 API read failed")
        require(
            api_status == 200
            and "application/json" in api_headers.get("content-type", "")
            and json.loads(api_body).get("ok") is True,
            "embedded dashboard /api/health route did not succeed",
        )
        login_asset_match = re.search(rb'(?:src|href)="(/assets/[^"]+)"', login_html)
        require(login_asset_match is not None, "TinyAuth login shell did not expose an asset")
        login_asset_path = login_asset_match.group(1).decode()
        login_asset_status, _, _, login_asset_body = public_client.request(AUTH_URL + login_asset_path)
        require(login_asset_status == 200 and login_asset_body, "TinyAuth login asset did not load")
        assert_static_accessibility_heuristic(login_html, login_asset_body, dashboard_body, asset_body)
        print("PASS static accessibility heuristic; U12 real-browser keyboard and screen-reader acceptance remains required")
        print("PASS authenticated SPA, /api, /v0, health, and asset")

        def open_real_sse(
            client: PublicCookieClient,
            cursor: str | None,
            label: str,
        ) -> tuple[LoopbackHTTPSConnection, http.client.HTTPResponse]:
            headers = {
                "Accept": "text/event-stream",
                "Sec-Fetch-Site": "same-origin",
            }
            if cursor:
                headers["Last-Event-ID"] = cursor
            stream_connection, stream_response = client.open_stream(
                DASHBOARD_URL + "/v0/events/stream",
                headers,
            )
            require(stream_response.status == 200, f"{label} supervisor SSE did not open through public HTTPS")
            stream_headers = {key.lower(): value for key, value in stream_response.getheaders()}
            require("text/event-stream" in stream_headers.get("content-type", ""), f"{label} SSE content type was lost")
            require("no-cache" in stream_headers.get("cache-control", ""), f"{label} SSE cache contract was lost")
            return stream_connection, stream_response

        def read_sse_event(
            response: http.client.HTTPResponse,
            label: str,
        ) -> tuple[str, str]:
            event_id = ""
            data: list[str] = []
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    line = response.readline()
                except (OSError, TimeoutError) as error:
                    raise Failure(f"{label} supervisor SSE read failed: {error}") from error
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace")
                if decoded.startswith("id:"):
                    event_id = decoded[3:].strip()
                elif decoded.startswith("data:"):
                    data.append(decoded[5:].lstrip())
                elif decoded in ("\n", "\r\n") and (event_id or data):
                    require(event_id, f"{label} supervisor SSE event had no id")
                    return event_id, "\n".join(data)
            raise Failure(f"{label} supervisor SSE did not deliver a complete event")

        def check_helper_sse(client: PublicCookieClient, cursor: str) -> None:
            helper_connection, helper_response = client.open_stream(
                DASHBOARD_URL + "/__fixture/sse",
                {
                    "Accept": "text/event-stream",
                    "Sec-Fetch-Site": "same-origin",
                    "Last-Event-ID": cursor,
                },
            )
            try:
                require(helper_response.status == 200, "relay SSE contract endpoint did not open")
                helper_headers = {key.lower(): value for key, value in helper_response.getheaders()}
                require(helper_headers.get("x-d2b-sse-buffering") == "off", "relay buffering header contract is missing")
                started = time.monotonic()
                first_line = helper_response.readline()
                require(time.monotonic() - started < 0.6, "SSE first event was buffered")
                require(first_line == f"id: {cursor}\n".encode(), "Last-Event-ID was not preserved by relay")
            finally:
                helper_connection.close()

        initial_stream_connection, initial_stream_response = open_real_sse(
            public_client,
            None,
            "initial",
        )
        try:
            initial_trigger_status, _, _, _ = public_client.request(
                DASHBOARD_URL + "/health",
                headers={"Sec-Fetch-Site": "same-origin"},
            )
            require(initial_trigger_status == 200, "initial SSE trigger request failed")
            pre_restart_event_id, _ = read_sse_event(initial_stream_response, "initial")
        finally:
            initial_stream_connection.close()
        check_helper_sse(public_client, "fixture-cursor")
        print(
            "PASS public HTTPS supervisor SSE event capture and helper "
            f"Last-Event-ID fidelity (cursor={pre_restart_event_id})"
        )

        mutation_headers = {
            "Content-Type": "application/json",
            "Origin": ORIGIN,
            "Sec-Fetch-Site": "same-origin",
        }
        mutation_body = b'{"suspended":true}'
        missing_status, _, _, _ = public_client.request(
            DASHBOARD_URL + "/v0/city/city",
            "PATCH",
            mutation_headers,
            mutation_body,
        )
        require(missing_status == 403, "mutation without X-GC-Request was accepted")
        wrong_origin = {**mutation_headers, "Origin": "https://wrong.example.test", "X-GC-Request": "fixture"}
        for unsafe_method in ("POST", "PUT", "PATCH", "DELETE"):
            wrong_origin_status, _, _, _ = public_client.request(
                DASHBOARD_URL + "/v0/city/city",
                unsafe_method,
                wrong_origin,
                mutation_body,
            )
            require(wrong_origin_status == 403, f"cross-origin {unsafe_method} mutation was accepted")
        cross_site = {**mutation_headers, "Sec-Fetch-Site": "cross-site", "X-GC-Request": "fixture"}
        cross_site_status, _, _, _ = public_client.request(
            DASHBOARD_URL + "/v0/city/city",
            "PATCH",
            cross_site,
            mutation_body,
        )
        require(cross_site_status == 403, "cross-site mutation was accepted")
        allowed = {**mutation_headers, "X-GC-Request": "dashboard"}
        allowed_status, _, _, _ = public_client.request(
            DASHBOARD_URL + "/v0/city/city",
            "PATCH",
            allowed,
            mutation_body,
        )
        require(allowed_status == 200, "same-origin mutation with native request header failed")
        restore_body = b'{"suspended":false}'
        restore_status, _, _, _ = public_client.request(
            DASHBOARD_URL + "/v0/city/city",
            "PATCH",
            allowed,
            restore_body,
        )
        require(restore_status == 200, "fixture city restore mutation failed")
        forwarded_noise = {
            **allowed,
            "X-Forwarded-Host": "wrong.example.test",
            "X-Forwarded-Proto": "http",
            "X-Forwarded-Port": "80",
            "X-Forwarded-For": "203.0.113.77",
        }
        forwarded_status, _, _, _ = public_client.request(
            DASHBOARD_URL + "/v0/city/city",
            "PATCH",
            forwarded_noise,
            mutation_body,
        )
        require(forwarded_status == 200, "forged X-Forwarded-* headers changed a valid mutation decision")
        forwarded_restore_status, _, _, _ = public_client.request(
            DASHBOARD_URL + "/v0/city/city",
            "PATCH",
            forwarded_noise,
            restore_body,
        )
        require(forwarded_restore_status == 200, "fixture city restore after forwarded-header proof failed")
        print("PASS same-origin dashboard mutation, cross-site rejection, and forwarded-header neutrality")

        wrong_host_status, _, _, _ = public_client.request(
            DASHBOARD_URL + "/health",
            headers={"Host": "wrong.example.test", "Sec-Fetch-Site": "same-origin"},
        )
        direct_wrong_status, _, _, _ = direct(
            "/health",
            headers={"Host": "wrong.example.test"},
        )
        require(wrong_host_status == 421 and direct_wrong_status == 421, "wrong Host was not rejected by supervisor")
        direct_forged_status, _, _, _ = direct(
            "/health",
            headers={
                "X-Forwarded-Host": "wrong.example.test",
                "X-Forwarded-Proto": "http",
                "X-Forwarded-Port": "80",
                "X-Forwarded-For": "203.0.113.77",
            },
        )
        require(direct_forged_status == 200, "forged X-Forwarded headers changed direct supervisor Host decisions")
        print("PASS wrong Host rejection and supervisor forwarded-header neutrality")

        cross_login_client = PublicCookieClient(tls_port, certificate, source_address="127.0.0.4")
        unknown_origin_status, unknown_origin_headers, _, _ = cross_login_client.request(
            AUTH_URL + "/api/user/login",
            "POST",
            {
                **auth_mutation_headers(),
                "Origin": "https://evil.example.test",
                "Referer": AUTH_ORIGIN + "/login",
                "Sec-Fetch-Site": "same-origin",
            },
            json.dumps({"username": FAKE_USER, "password": FAKE_PASSWORD}).encode(),
        )
        require(
            unknown_origin_status == 403 and "set-cookie" not in unknown_origin_headers,
            "unknown nonempty auth Origin was not rejected",
        )
        cross_login_status, cross_login_headers, _, _ = cross_login_client.request(
            AUTH_URL + "/api/user/login",
            "POST",
            {
                **auth_mutation_headers(),
                "Origin": "https://evil.example.test",
                "Referer": "https://evil.example.test/login",
                "Sec-Fetch-Site": "cross-site",
            },
            json.dumps({"username": FAKE_USER, "password": FAKE_PASSWORD}).encode(),
        )
        require(cross_login_status == 403 and "set-cookie" not in cross_login_headers, "cross-site login was not rejected without a cookie")
        cross_logout_status, _, _, _ = public_client.request(
            AUTH_URL + "/api/user/logout",
            "POST",
            {
                "Origin": "https://evil.example.test",
                "Referer": "https://evil.example.test/logout",
                "Sec-Fetch-Site": "cross-site",
            },
        )
        require(cross_logout_status == 403, "cross-site logout was not rejected")
        logout_status, _, _, _ = public_client.request(
            AUTH_URL + "/api/user/logout",
            "POST",
            {
                "Origin": AUTH_ORIGIN,
                "Referer": AUTH_ORIGIN + "/login",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        require(logout_status in (200, 204, 302), "TinyAuth logout did not complete")
        old_cookie_header = public_client.cookie_header(DASHBOARD_URL + "/health")
        old_cookie_status, _, _, _ = public_client.request(
            DASHBOARD_URL + "/health",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        require(old_cookie_status == 302, "logged-out cookie was still accepted")
        if old_cookie_header:
            print("NOTE logout response left an expired cookie in the jar; the server rejected it")
        reauth_status, _, _, _ = login(public_client, FAKE_PASSWORD)
        require(reauth_status in (200, 204, 302), "reauthentication after logout failed")
        print("PASS valid auth mutations, unknown/cross-site login/logout rejection, logout invalidation, and reauthentication")

        invalid_client = PublicCookieClient(tls_port, certificate, source_address="127.0.0.4")
        for attempt in range(2):
            invalid_status, invalid_headers, _, _ = login(
                invalid_client,
                f"fixture-invalid-password-{attempt}",
                username=f"invalid-user-{attempt}",
                require_cookie=False,
            )
            require(invalid_status in (401, 403), "pre-limit wrong-password attempt was not rejected")
            require("set-cookie" not in invalid_headers, "wrong-password attempt emitted Set-Cookie")
        rate_statuses = []
        for attempt in range(4):
            rate_status, rate_headers, _, _ = login(
                rate_client,
                "fixture-invalid-password",
                username=f"rate-user-{attempt}",
                require_cookie=False,
            )
            rate_statuses.append(rate_status)
            if attempt < 3:
                require(rate_status in (401, 403), "relay rate-limit pre-limit attempt was not rejected as authentication failure")
                require("set-cookie" not in rate_headers, "relay rate-limit pre-limit attempt emitted Set-Cookie")
        require(rate_statuses[-1] == 429, f"relay rate limiter did not return 429 after its pre-limit failures: {rate_statuses}")
        print("PASS wrong-password no-cookie failures and independent relay rate limit")

        idle_client = PublicCookieClient(tls_port, certificate, source_address="127.0.0.6")
        idle_login_status, _, _, _ = login(idle_client, FAKE_PASSWORD)
        require(idle_login_status in (200, 204, 302), "idle-expiry login failed")
        time.sleep(FIXTURE_SESSION_EXPIRY + 1.0)
        idle_cookie_header = idle_client.cookie_header(DASHBOARD_URL + "/health")
        idle_status, _, _, _ = idle_client.request(DASHBOARD_URL + "/health", headers={"Sec-Fetch-Site": "same-origin"})
        require(idle_status == 302, "idle-expired cookie was still accepted")
        if idle_cookie_header:
            print("NOTE idle expiry left an expired cookie in the jar; the server rejected it")
        print(f"PASS idle session expiry ({FIXTURE_SESSION_EXPIRY}s)")

        absolute_client = PublicCookieClient(tls_port, certificate, source_address="127.0.0.5")
        absolute_login_status, _, _, _ = login(absolute_client, FAKE_PASSWORD)
        require(absolute_login_status in (200, 204, 302), "absolute-expiry login failed")
        absolute_started = time.monotonic()
        active_until = absolute_started + FIXTURE_SESSION_MAX_LIFETIME - 0.75
        while time.monotonic() < active_until:
            active_status, active_headers, _, active_body = absolute_client.request(
                DASHBOARD_URL + "/api/health",
                headers={"Sec-Fetch-Site": "same-origin"},
            )
            if active_status is None:
                time.sleep(0.2)
                active_status, active_headers, _, active_body = absolute_client.request(
                    DASHBOARD_URL + "/api/health",
                    headers={"Sec-Fetch-Site": "same-origin"},
                )
            require(
                active_status == 200 and json.loads(active_body).get("ok") is True,
                "authenticated activity did not refresh the idle session before absolute expiry: "
                f"status={active_status}, elapsed={time.monotonic() - absolute_started:.2f}, "
                f"set_cookie={'set-cookie' in active_headers}, body={active_body[:160]!r}, "
                f"error={absolute_client.last_error}",
            )
            time.sleep(0.5)
        remaining = absolute_started + FIXTURE_SESSION_MAX_LIFETIME + 2.0 - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        absolute_status, absolute_headers, _, _ = absolute_client.request(
            DASHBOARD_URL + "/api/health",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        require(
            absolute_status == 302,
            "absolute session lifetime was extended by active traffic: "
            f"status={absolute_status}, elapsed={time.monotonic() - absolute_started:.2f}, "
            f"set_cookie={'set-cookie' in absolute_headers}",
        )
        print(f"PASS active absolute session expiry ({FIXTURE_SESSION_MAX_LIFETIME}s)")

        def stop_tinyauth(label: str) -> None:
            nonlocal tinyauth
            stop_owned(tinyauth)
            wait_port_closed(tinyauth_port)
            require(tinyauth.poll() is not None, f"{label} TinyAuth process remained alive")
            require(nginx.poll() is None, f"{label} relay stopped with TinyAuth")
            stopped_status, _, _, _ = inner_relay(
                "/health",
                source_address=TLS_SOURCE_ADDRESS,
            )
            require(
                stopped_status in (401, 403, 500, 502, 503, 504),
                f"{label} relay did not fail closed while TinyAuth was stopped: "
                f"status={stopped_status}",
            )

        def start_tinyauth(label: str) -> None:
            nonlocal tinyauth
            tinyauth = spawn(
                [str(runtime / "bin" / "tinyauth"), "--configfile", str(base / "tinyauth.yml")],
                label,
            )
            wait_port(tinyauth_port)
            require(tinyauth.poll() is None, f"{label} TinyAuth process exited during startup")
            require(nginx.pid == relay_pid, f"{label} relay was restarted with TinyAuth")
            wait_until(
                lambda: inner_auth("/api/auth/nginx", source_address=TLS_SOURCE_ADDRESS)[0] in (200, 401),
                15,
                f"{label} TinyAuth did not become ready",
            )

        rotated_hash = create_user_hash(ROTATED_PASSWORD)
        user_rotation_client = PublicCookieClient(tls_port, certificate, source_address="127.0.0.7")
        user_login_status, _, _, _ = login(user_rotation_client, FAKE_PASSWORD)
        require(
            user_login_status in (200, 204, 302),
            f"user-rotation baseline login failed: status={user_login_status}",
        )
        state_path = base / "tinyauth.db"
        require(state_path.exists(), "TinyAuth did not create retained session state")
        stop_tinyauth("tinyauth-user-rotation-stopped.log")
        users_path.write_text(rotated_hash + "\n", encoding="utf-8")
        users_path.chmod(0o600)
        start_tinyauth("tinyauth-user-rotation-after-users.log")
        old_password_client = PublicCookieClient(tls_port, certificate, source_address="127.0.0.8")
        old_password_status, old_password_headers, _, _ = login(
            old_password_client,
            FAKE_PASSWORD,
            require_cookie=False,
        )
        require(old_password_status in (401, 403) and "set-cookie" not in old_password_headers, "old password remained accepted after stopped user rotation")
        retained_cookie_status, _, _, _ = user_rotation_client.request(
            DASHBOARD_URL + "/health",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        require(retained_cookie_status in (200, 302), "user-removal cookie behavior was not observable")
        print(
            "PASS stopped user rotation with retained TinyAuth state; "
            + ("existing cookie invalidated" if retained_cookie_status == 302 else "existing cookie retained")
        )

        state_rotation_client = PublicCookieClient(tls_port, certificate, source_address="127.0.0.9")
        state_login_status, _, _, _ = login(state_rotation_client, ROTATED_PASSWORD)
        require(state_login_status in (200, 204, 302), "session-state rotation baseline login failed")
        stop_tinyauth("tinyauth-session-state-rotation-stopped.log")
        for suffix in ("", "-wal", "-shm"):
            (base / f"tinyauth.db{suffix}").unlink(missing_ok=True)
        require(
            not any((base / f"tinyauth.db{suffix}").exists() for suffix in ("", "-wal", "-shm")),
            "TinyAuth SQLite state remained after stopped state rotation",
        )
        start_tinyauth("tinyauth-session-state-rotation-after-state.log")
        rotated_state_cookie_status, _, _, _ = state_rotation_client.request(
            DASHBOARD_URL + "/health",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        require(rotated_state_cookie_status == 302, "pre-rotation cookie survived stopped session-state rotation")
        new_state_client = PublicCookieClient(tls_port, certificate, source_address="127.0.0.10")
        new_state_login_status, _, _, _ = login(new_state_client, ROTATED_PASSWORD)
        require(new_state_login_status in (200, 204, 302), "new credentials failed after stopped session-state rotation")
        print("PASS separate stopped session-state rotation invalidated the pre-rotation cookie")

        grant_key = base64.b64encode(b"fixture-write-grant-public-key-material"[:32]).decode()
        grant_client = PublicCookieClient(tls_port, certificate, source_address="127.0.0.11")
        grant_login_status, _, _, _ = login(grant_client, ROTATED_PASSWORD)
        require(grant_login_status in (200, 204, 302), "grant-auth negative baseline login failed")
        restart_supervisor(
            base_supervisor_config
            + f'write_auth_verify_key = "fixture:{grant_key}"\n',
            "supervisor-grant-auth.log",
        )
        grant_relogin_status, _, _, _ = login(grant_client, ROTATED_PASSWORD)
        require(grant_relogin_status in (200, 204, 302), "grant-auth negative reauthentication failed")
        grant_status, _, _, _ = grant_client.request(
            DASHBOARD_URL + "/v0/city/city",
            "PATCH",
            allowed,
            restore_body,
        )
        require(
            grant_status == 401,
            f"grant-auth enabled first-party mutation did not fail closed with 401: status={grant_status}",
        )
        restart_supervisor(
            base_supervisor_config
            + f'read_auth_verify_key = "fixture:{grant_key}"\n',
            "supervisor-read-grant-auth.log",
        )
        read_grant_relogin_status, _, _, _ = login(grant_client, ROTATED_PASSWORD)
        require(read_grant_relogin_status in (200, 204, 302), "read-grant-auth negative reauthentication failed")
        read_grant_status, _, _, _ = grant_client.request(
            DASHBOARD_URL + "/v0/city/city/status",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        require(
            read_grant_status == 401,
            f"grant-auth enabled first-party read did not fail closed with 401: status={read_grant_status}",
        )
        restart_supervisor(base_supervisor_config, "supervisor-after-grant-auth.log")
        print("PASS bounded write/read grant-auth negatives for grant-less first-party API")

        recovery_client = PublicCookieClient(tls_port, certificate, source_address="127.0.0.12")
        recovery_login_status, _, _, _ = login(recovery_client, ROTATED_PASSWORD)
        require(recovery_login_status in (200, 204, 302), "supervisor recovery baseline login failed")
        stop_owned(supervisor)
        unavailable = False
        for _ in range(30):
            unavailable_status, _, _, _ = recovery_client.request(
                DASHBOARD_URL + "/health",
                headers={"Sec-Fetch-Site": "same-origin"},
            )
            if unavailable_status in (502, 503, 504):
                unavailable = True
                break
            time.sleep(0.1)
        require(
            unavailable,
            "relay did not report temporary supervisor unavailability: "
            f"last_status={unavailable_status}, cookie={bool(recovery_client.cookie_header(DASHBOARD_URL + '/health'))}",
        )
        supervisor_config_path.write_text(base_supervisor_config, encoding="utf-8")
        supervisor = spawn(
            [str(runtime / "bin" / "gc"), "supervisor", "run"],
            "supervisor-restart.log",
        )
        wait_port(supervisor_port)
        require(supervisor.poll() is None, "restarted fixture supervisor exited before SSE recovery")
        wait_until(city_ready, 90, "authenticated reads did not recover after supervisor restart")
        recovery_relogin_status, _, _, _ = login(recovery_client, ROTATED_PASSWORD)
        require(recovery_relogin_status in (200, 204, 302), "supervisor recovery reauthentication failed")
        reload_status, _, _, reload_body = recovery_client.request(
            DASHBOARD_URL + "/",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        require(
            reload_status == 200 and b"<html" in reload_body.lower(),
            "authoritative dashboard reload did not complete after supervisor restart",
        )
        after_restart_connection, after_restart_response = open_real_sse(
            recovery_client,
            pre_restart_event_id,
            "after-restart",
        )
        try:
            post_restart_trigger_status, _, _, _ = recovery_client.request(
                DASHBOARD_URL + "/health",
                headers={"Sec-Fetch-Site": "same-origin"},
            )
            require(post_restart_trigger_status == 200, "post-restart SSE trigger request failed")
            post_restart_event_id, _ = read_sse_event(
                after_restart_response,
                "after-restart",
            )
        finally:
            after_restart_connection.close()
        if pre_restart_event_id.isdigit() and post_restart_event_id.isdigit():
            require(
                int(post_restart_event_id) > int(pre_restart_event_id),
                "post-restart SSE cursor did not advance",
            )
        else:
            require(
                post_restart_event_id != pre_restart_event_id,
                "post-restart SSE cursor did not change",
            )
        check_helper_sse(recovery_client, post_restart_event_id)
        recovered_status, _, _, _ = recovery_client.request(
            DASHBOARD_URL + "/health",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        require(recovered_status == 200, "relay health did not recover after supervisor restart")
        print(
            "PASS supervisor restart, authoritative SPA reload, real SSE "
            f"Last-Event-ID reconnect, post-restart delivery ({pre_restart_event_id} -> "
            f"{post_restart_event_id}), and helper fidelity"
        )

        issued_cookie_values = {
            value
            for client in PublicCookieClient.instances
            for value in client.issued_cookie_values
        }
        secret_values = (
            FAKE_PASSWORD,
            ROTATED_PASSWORD,
            "fixture-invalid-password",
            "fixture-invalid-password-0",
            "fixture-invalid-password-1",
            user_hash,
            rotated_hash,
            *sorted(issued_cookie_values),
        )
        for log_path in base.glob("*.log"):
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            require(
                all(secret not in log_text for secret in secret_values),
                f"auth secret material appeared in {log_path.name}",
            )
        command_lines = [
            command
            for _, (_, _, command) in proc_snapshot(
                base,
                {tinyauth.pid, nginx.pid, supervisor.pid},
            ).items()
        ]
        require(
            all(secret not in command for secret in secret_values for command in command_lines),
            "auth secret material appeared in a long-lived argv",
        )
        print("PASS auth secrets absent from long-lived argv and logs")

        config_text = supervisor_config_path.read_text(encoding="utf-8")
        require(
            'bind = "127.0.0.1"' in config_text
            and f"port = {SUPERVISOR_PORT}" in config_text
            and f'allowed_hosts = ["{DASHBOARD_HOST}"]' in config_text,
            "supervisor config does not match the fixed loopback split-host contract",
        )
        for forbidden in ("allowed_origins", "allow_mutations", "write_auth_", "read_auth_"):
            require(forbidden not in config_text, f"supervisor config unexpectedly contains {forbidden}")
        print("PASS fixed loopback supervisor, split external Host, and absent grant/CORS overrides")
        print(f"PASS exact runtime pins: Gas City {BUILD_ID}, TinyAuth {TINYAUTH_VERSION}, Nginx {NGINX_VERSION}")
        print("PASS U8 ingress fixture")
        outcome = 0
    except (Failure, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"FAIL U8 ingress fixture: {error}", file=sys.stderr)
        outcome = 1
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
            outcome = 1
        try:
            shutil.rmtree(base)
        except OSError as error:
            print(f"FAIL fixture cleanup: could not remove {base}: {error}", file=sys.stderr)
            outcome = 1
        if base.exists():
            print(f"FAIL fixture cleanup residue: {base}", file=sys.stderr)
            outcome = 1
    return outcome


def wait_until(predicate, timeout: float, label: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.25)
    raise Failure(label)


if __name__ == "__main__":
    raise SystemExit(main())
