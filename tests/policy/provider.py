from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import os
import pathlib
import stat
import tempfile
import tomllib
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
CITY = ROOT / "city" / "city.toml"
PROVIDER_SCRIPT = ROOT / "scripts" / "copilot-provider.py"


def _load_provider_module():
    spec = importlib.util.spec_from_file_location(
        "copilot_provider_for_tests",
        PROVIDER_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Copilot provider")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROVIDER = _load_provider_module()

EXPECTED = {
    "copilot-planning-grok": ("planning-grok", "planning"),
    "copilot-review": ("review", "review"),
    "copilot-review-grok": ("review-grok", "review"),
    "copilot-review-luna": ("review-luna", "review"),
    "copilot-code-luna": ("code-luna", "coding"),
}


class ProviderPolicyTests(unittest.TestCase):
    TEST_EUID = 4242

    @staticmethod
    def _stat_view(
        info: os.stat_result,
        *,
        uid: int,
        mode: int | None = None,
        dev: int | None = None,
        ino: int | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            st_mode=info.st_mode if mode is None else stat.S_IFREG | mode,
            st_uid=uid,
            st_size=info.st_size,
            st_dev=info.st_dev if dev is None else dev,
            st_ino=info.st_ino if ino is None else ino,
        )

    @contextmanager
    def _credential_stats(
        self,
        path: pathlib.Path,
        *,
        owner_uid: int,
        opened_uid: int | None = None,
        lstat_mode: int | None = None,
        opened_mode: int | None = None,
        opened_dev: int | None = None,
        opened_ino: int | None = None,
    ):
        real_lstat = pathlib.Path.lstat
        real_fstat = os.fstat

        def fake_lstat(candidate: pathlib.Path) -> SimpleNamespace | os.stat_result:
            info = real_lstat(candidate)
            if candidate == path:
                return self._stat_view(
                    info,
                    uid=owner_uid,
                    mode=lstat_mode,
                )
            return info

        def fake_fstat(descriptor: int) -> SimpleNamespace:
            info = real_fstat(descriptor)
            return self._stat_view(
                info,
                uid=owner_uid if opened_uid is None else opened_uid,
                mode=opened_mode,
                dev=opened_dev,
                ino=opened_ino,
            )

        with (
            mock.patch.object(PROVIDER.os, "geteuid", return_value=self.TEST_EUID),
            mock.patch.object(PROVIDER.pathlib.Path, "lstat", new=fake_lstat),
            mock.patch.object(PROVIDER.os, "fstat", side_effect=fake_fstat),
        ):
            yield

    def _write_credential(self, directory: pathlib.Path) -> pathlib.Path:
        path = directory / "copilot-token"
        path.write_text("fixture-token\n", encoding="ascii")
        path.chmod(0o600)
        return path

    @contextmanager
    def _temporary_directory(self):
        scratch = pathlib.Path(
            os.environ.get("D2B_GASCITY_CHECK_RUN_ROOT", ROOT / ".scratch")
        )
        created = not scratch.exists()
        scratch.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(
                dir=scratch,
                prefix="provider-policy-",
            ) as raw_directory:
                yield pathlib.Path(raw_directory)
        finally:
            if created:
                scratch.rmdir()

    def _assert_credential_invalid(self, argument: str | None) -> None:
        with self.assertRaises(PROVIDER.ProviderError) as context:
            PROVIDER._read_credential(argument)
        self.assertEqual(context.exception.code, "credential-invalid")

    @contextmanager
    def _projected_credential(
        self,
        path: pathlib.Path,
        **stats: int | None,
    ):
        with (
            mock.patch.dict(
                PROVIDER.os.environ,
                {"CREDENTIALS_DIRECTORY": str(path.parent)},
                clear=False,
            ),
            self._credential_stats(path, **stats),
        ):
            yield

    def test_systemd_projection_accepts_root_owned_credential_modes(self) -> None:
        for mode in (0o400, 0o440):
            with self.subTest(mode=oct(mode)):
                with self._temporary_directory() as directory:
                    path = self._write_credential(directory)
                    path.chmod(mode)
                    with self._projected_credential(
                        path,
                        owner_uid=0,
                        opened_uid=0,
                    ):
                        self.assertEqual(
                            PROVIDER._read_credential(None),
                            "fixture-token",
                        )

    def test_systemd_projection_rejects_wrong_owner(self) -> None:
        with self._temporary_directory() as directory:
            path = self._write_credential(directory)
            path.chmod(0o440)
            with self._projected_credential(path, owner_uid=1234):
                self._assert_credential_invalid(None)

    def test_explicit_credential_rejects_foreign_root_owner(self) -> None:
        with self._temporary_directory() as directory:
            path = self._write_credential(directory)
            with self._credential_stats(path, owner_uid=0):
                self._assert_credential_invalid(str(path))

    def test_systemd_projection_rejects_unsafe_modes_at_lstat_and_fstat(self) -> None:
        for mode in (0o600, 0o640, 0o444, 0o450):
            with self.subTest(mode=oct(mode)):
                with self._temporary_directory() as directory:
                    path = self._write_credential(directory)
                    path.chmod(0o400)
                    with self._projected_credential(
                        path,
                        owner_uid=0,
                        opened_uid=0,
                        lstat_mode=mode,
                    ):
                        self._assert_credential_invalid(None)
                    with self._projected_credential(
                        path,
                        owner_uid=0,
                        opened_uid=0,
                        lstat_mode=0o400,
                        opened_mode=mode,
                    ):
                        self._assert_credential_invalid(None)

    def test_explicit_credential_rejects_0440_mode(self) -> None:
        with self._temporary_directory() as directory:
            path = self._write_credential(directory)
            path.chmod(0o440)
            with self._credential_stats(
                path,
                owner_uid=self.TEST_EUID,
                opened_uid=self.TEST_EUID,
            ):
                self._assert_credential_invalid(str(path))
            with self._credential_stats(
                path,
                owner_uid=self.TEST_EUID,
                opened_uid=self.TEST_EUID,
                lstat_mode=0o400,
                opened_mode=0o440,
            ):
                self._assert_credential_invalid(str(path))

    def test_projection_keeps_mode_symlink_and_identity_checks(self) -> None:
        with self._temporary_directory() as directory:
            path = self._write_credential(directory)
            path.chmod(0o440)
            with self._projected_credential(
                path,
                owner_uid=0,
                opened_uid=1234,
            ):
                self._assert_credential_invalid(None)

            path.chmod(0o644)
            with self._projected_credential(
                path,
                owner_uid=0,
                opened_uid=0,
            ):
                self._assert_credential_invalid(None)

            target = directory / "target"
            target.write_text("fixture-token\n", encoding="ascii")
            target.chmod(0o600)
            path.unlink()
            path.symlink_to(target)
            with self._projected_credential(
                path,
                owner_uid=0,
                opened_uid=0,
            ):
                self._assert_credential_invalid(None)

            path.unlink()
            path = self._write_credential(directory)
            path.chmod(0o440)
            real_info = path.stat()
            with self._projected_credential(
                path,
                owner_uid=0,
                opened_uid=0,
                opened_dev=real_info.st_dev,
                opened_ino=real_info.st_ino + 1,
            ):
                self._assert_credential_invalid(None)

    def test_acp_identity_rejects_controls_and_oversized_values(self) -> None:
        cases = (
            {
                "GC_SESSION_NAME": "fixture\nsession",
                "GC_SESSION_ID": "fixture-session-id",
                "GC_INSTANCE_TOKEN": "fixture-instance-token",
                "GC_RUNTIME_EPOCH": "fixture-runtime-epoch",
            },
            {
                "GC_SESSION_NAME": "fixture-session",
                "GC_SESSION_ID": "x" * (PROVIDER.MAX_ACP_IDENTITY_BYTES + 1),
                "GC_INSTANCE_TOKEN": "fixture-instance-token",
                "GC_RUNTIME_EPOCH": "fixture-runtime-epoch",
            },
        )
        for identity in cases:
            with self.subTest(identity=identity):
                with self._temporary_directory() as directory:
                    meta_dir = directory / "gc-acp"
                    environment = {
                        **identity,
                        "TMPDIR": str(directory),
                    }
                    with (
                        mock.patch.dict(
                            PROVIDER.os.environ,
                            environment,
                            clear=True,
                        ),
                        self.assertRaises(PROVIDER.ProviderError) as context,
                    ):
                        PROVIDER._seed_acp_identity()
                    self.assertEqual(
                        context.exception.code,
                        "acp-identity-invalid",
                    )
                    self.assertFalse(meta_dir.exists())

    def test_portable_providers_inherit_builtin_copilot(self) -> None:
        config = tomllib.loads(CITY.read_text(encoding="utf-8"))
        providers = config.get("providers", {})
        self.assertEqual(set(providers), set(EXPECTED))
        expected_args = {
            "copilot-planning-grok": [
                "--yolo",
                "--model",
                "grok-4.6",
                "--context",
                "long_context",
                "--effort",
                "high",
            ],
            "copilot-review": [
                "--yolo",
                "--model",
                "grok-4.6",
                "--context",
                "long_context",
                "--effort",
                "high",
            ],
            "copilot-review-grok": [
                "--yolo",
                "--model",
                "grok-4.6",
                "--context",
                "long_context",
                "--effort",
                "high",
            ],
            "copilot-review-luna": [
                "--yolo",
                "--model",
                "gpt-5.6-luna",
                "--context",
                "long_context",
                "--effort",
                "max",
            ],
            "copilot-code-luna": [
                "--yolo",
                "--model",
                "gpt-5.6-luna",
                "--context",
                "default",
                "--effort",
                "max",
            ],
        }
        for name, args in expected_args.items():
            with self.subTest(provider=name):
                provider = providers[name]
                self.assertEqual(provider["base"], "builtin:copilot")
                self.assertEqual(provider["args"], args)
                self.assertEqual(
                    provider["env"],
                    {
                        "COPILOT_ALLOW_ALL": "true",
                        "COPILOT_GITHUB_TOKEN": "$COPILOT_GITHUB_TOKEN",
                        "GH_TOKEN": "$COPILOT_GITHUB_TOKEN",
                    },
                )
                self.assertNotIn("command", provider)
                self.assertNotIn("acp_command", provider)
                self.assertNotIn("supports_acp", provider)

    def test_tool_policies_are_closed(self) -> None:
        config = tomllib.loads(CITY.read_text(encoding="utf-8"))
        providers = config["providers"]
        for name in EXPECTED:
            self.assertEqual(providers[name]["args"][0], "--yolo")
        self.assertNotIn("allow-all", CITY.read_text(encoding="utf-8"))

    def test_profiles_are_grok_and_luna_only(self) -> None:
        self.assertEqual(
            PROVIDER.PROFILES,
            {
                "planning-grok": {
                    "model": "grok-4.6",
                    "context": "long_context",
                    "effort": "high",
                },
                "review-grok": {
                    "model": "grok-4.6",
                    "context": "long_context",
                    "effort": "high",
                },
                "review-luna": {
                    "model": "gpt-5.6-luna",
                    "context": "long_context",
                    "effort": "max",
                },
                "code-luna": {
                    "model": "gpt-5.6-luna",
                    "context": "default",
                    "effort": "max",
                },
            },
        )

    def test_wrapper_is_packaged_source_and_executable(self) -> None:
        self.assertTrue(PROVIDER_SCRIPT.is_file())
        self.assertTrue(PROVIDER_SCRIPT.stat().st_mode & stat.S_IXUSR)

    def test_publisher_uses_official_copilot_tmux(self) -> None:
        config = tomllib.loads(CITY.read_text(encoding="utf-8"))
        publisher = next(
            patch
            for patch in config["patches"]["agent"]
            if patch["dir"] == "d2b" and patch["name"] == "publisher"
        )
        self.assertEqual(publisher["provider"], "copilot-code-luna")
        self.assertEqual(publisher["session"], "")
        self.assertNotIn("start_command", publisher)
        self.assertNotIn("lifecycle", publisher)

    def test_provider_surface_has_no_second_lifecycle_or_transport(self) -> None:
        paths = [
            CITY,
            ROOT / "city" / "providers",
            PROVIDER_SCRIPT,
            ROOT / "tests" / "acceptance" / "copilot-acp.py",
            ROOT / "tests" / "fixtures" / "acp",
        ]
        forbidden = (
            "agent-launcher",
            "agent server",
            "fdproxy",
            "session.db",
            "session database",
            "retry ledger",
            "retry_ledger",
            "per-child",
            "custom lifecycle service",
        )
        for path in paths:
            candidates = [path] if path.is_file() else sorted(path.rglob("*"))
            for candidate in candidates:
                if not candidate.is_file() or candidate.suffix not in {
                    ".json",
                    ".md",
                    ".py",
                    ".toml",
                }:
                    continue
                text = candidate.read_text(encoding="utf-8").lower()
                for marker in forbidden:
                    self.assertNotIn(
                        marker,
                        text,
                        f"{marker} in {candidate.relative_to(ROOT)}",
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
