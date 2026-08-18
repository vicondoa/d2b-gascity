from __future__ import annotations

import http.client
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _find_binary(name: str, *absolute_paths: str) -> str | None:
    candidates = [
        os.environ.get(name.upper().replace("-", "_")),
        shutil.which(name),
        *absolute_paths,
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class BackendHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        response = (
            f"method={self.command}\n"
            f"path={self.path}\n"
            f"body={body.decode('utf-8')}\n"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def do_GET(self) -> None:
        if self.path != "/events":
            self.send_error(404)
            return
        response = b"event: fixture\ndata: through-proxy\n\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)
        self.wfile.flush()

    def log_message(self, *_args: object) -> None:
        pass


class ApiProxyFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        proxy = _find_binary(
            "systemd-socket-proxyd",
            "/run/current-system/sw/lib/systemd/systemd-socket-proxyd",
            "/usr/lib/systemd/systemd-socket-proxyd",
            "/lib/systemd/systemd-socket-proxyd",
        )
        activate = _find_binary(
            "systemd-socket-activate",
            "/run/current-system/sw/bin/systemd-socket-activate",
            "/usr/bin/systemd-socket-activate",
            "/bin/systemd-socket-activate",
        )
        if proxy is None or activate is None:
            self.skipTest("systemd socket activation tools are unavailable")

        self.backend = ThreadingHTTPServer(("127.0.0.1", 0), BackendHandler)
        self.backend_thread = threading.Thread(
            target=self.backend.serve_forever,
            daemon=True,
        )
        self.backend_thread.start()
        self.proxy_port = _free_port()
        self.process = subprocess.Popen(
            [
                activate,
                "--listen",
                f"127.0.0.1:{self.proxy_port}",
                proxy,
                f"127.0.0.1:{self.backend.server_port}",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            text=True,
        )
        self._wait_for_listener()

    def tearDown(self) -> None:
        if hasattr(self, "process"):
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=5)
            if self.process.stdout is not None:
                self.process.stdout.close()
            if self.process.stderr is not None:
                self.process.stderr.close()
        if hasattr(self, "backend"):
            self.backend.shutdown()
            self.backend.server_close()
            self.backend_thread.join(timeout=5)

    def _wait_for_listener(self) -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                details = self.process.stderr.read()
                self.fail(f"socket activation exited: {details}")
            try:
                with socket.create_connection(
                    ("127.0.0.1", self.proxy_port),
                    timeout=0.2,
                ):
                    return
            except OSError:
                time.sleep(0.05)
        self.fail("socket activation did not open its loopback listener")

    def test_http_method_body_and_sse_reach_backend_unchanged(self) -> None:
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.proxy_port,
            timeout=5,
        )
        connection.request(
            "POST",
            "/echo?fixture=1",
            body=b"method-body",
            headers={"Content-Length": "11"},
        )
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.read(),
            b"method=POST\npath=/echo?fixture=1\nbody=method-body\n",
        )
        connection.close()

        connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.proxy_port,
            timeout=5,
        )
        connection.request(
            "GET",
            "/events",
            headers={
                "Accept": "text/event-stream",
                "Last-Event-ID": "fixture-7",
            },
        )
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/event-stream")
        self.assertEqual(
            response.read(),
            b"event: fixture\ndata: through-proxy\n\n",
        )
        connection.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
