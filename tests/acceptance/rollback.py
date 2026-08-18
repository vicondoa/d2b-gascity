#!/usr/bin/env python3
"""Credential-free U10 separate-root rollback acceptance fixture."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import stat
import tempfile
import unittest
from dataclasses import dataclass
from typing import Mapping


ROOT = pathlib.Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "tests" / "fixtures" / "rollback" / "rehearsal-receipt.example.json"
PROTOTYPE_ROOT_REF = "/var/lib/gascity-prototype"
STANDALONE_ROOT_REF = "/var/lib/d2b-gascity"
REQUIRED_RECEIPT_ROWS = frozenset(
    {
        "root_separation",
        "prototype_integrity",
        "old_service_state",
        "clean_standalone_root",
        "new_service_paths",
        "generation_rehearsal",
        "failed_new_start",
        "retained_closures",
        "offline_rollback",
        "expiry_and_destruction",
    }
)
FORBIDDEN_NEW_OPERATIONS = frozenset(
    {"copy", "chown", "convert", "read-write", "chmod"}
)


class Failure(AssertionError):
    """Raised when the fixture's modeled host contract is violated."""


class ReceiptError(ValueError):
    """Raised when a host rehearsal receipt does not match the schema."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_state(path: pathlib.Path) -> dict[str, object]:
    metadata = path.lstat()
    return {
        "mode": oct(stat.S_IMODE(metadata.st_mode)),
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "sha256": _sha256(path),
    }


def _tree_snapshot(root: pathlib.Path) -> dict[str, dict[str, object]]:
    candidates = [root, *sorted(root.rglob("*"))]
    snapshot: dict[str, dict[str, object]] = {}
    for candidate in candidates:
        relative = "." if candidate == root else candidate.relative_to(root).as_posix()
        metadata = candidate.lstat()
        kind = "directory" if stat.S_ISDIR(metadata.st_mode) else "file"
        entry: dict[str, object] = {
            "kind": kind,
            "mode": oct(stat.S_IMODE(metadata.st_mode)),
            "uid": metadata.st_uid,
            "gid": metadata.st_gid,
        }
        if kind == "file":
            entry["sha256"] = _sha256(candidate)
        snapshot[relative] = entry
    return snapshot


def _write(path: pathlib.Path, content: str, mode: int) -> None:
    path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    os.chmod(path, mode)


def _freeze_tree(root: pathlib.Path) -> None:
    for candidate in sorted(root.rglob("*"), reverse=True):
        os.chmod(candidate, 0o555 if candidate.is_dir() else 0o444)
    os.chmod(root, 0o555)


def _write_integrity_manifest(
    root: pathlib.Path,
    path: pathlib.Path,
) -> None:
    payload = {
        "schema": 1,
        "root": PROTOTYPE_ROOT_REF,
        "entries": _tree_snapshot(root),
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o444)


def _verify_integrity_manifest(root: pathlib.Path, path: pathlib.Path) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return (
        payload.get("schema") == 1
        and payload.get("root") == PROTOTYPE_ROOT_REF
        and payload.get("entries") == _tree_snapshot(root)
    )


def _load_receipt() -> dict[str, object]:
    try:
        value = json.loads(RECEIPT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReceiptError(f"cannot load rollback receipt example: {error}") from error
    if not isinstance(value, dict):
        raise ReceiptError("rollback receipt must be a JSON object")
    return value


def _validate_receipt(receipt: Mapping[str, object]) -> None:
    if receipt.get("schema") != 1:
        raise ReceiptError("rollback receipt schema must be 1")
    if receipt.get("kind") != "d2b-gascity-u10-rehearsal":
        raise ReceiptError("rollback receipt kind is not U10")
    if receipt.get("redacted") is not True:
        raise ReceiptError("rollback receipt must be redacted")
    if receipt.get("network_used") is not False:
        raise ReceiptError("rollback receipt must record no network for the fixture")
    rows = receipt.get("rows")
    if not isinstance(rows, dict):
        raise ReceiptError("rollback receipt rows must be an object")
    missing = sorted(REQUIRED_RECEIPT_ROWS - set(rows))
    if missing:
        raise ReceiptError(f"rollback receipt is missing rows: {', '.join(missing)}")
    for name in REQUIRED_RECEIPT_ROWS:
        row = rows[name]
        if not isinstance(row, dict) or not isinstance(row.get("status"), str):
            raise ReceiptError(f"rollback receipt row is malformed: {name}")


def _eligible_for_u12(receipt: Mapping[str, object]) -> bool:
    _validate_receipt(receipt)
    rows = receipt["rows"]
    assert isinstance(rows, dict)
    offline = rows["offline_rollback"]
    assert isinstance(offline, dict)
    return bool(
        receipt.get("host_generated") is True
        and receipt.get("redacted") is True
        and receipt.get("eligible_for_u12") is True
        and all(rows[name]["status"] == "pass" for name in REQUIRED_RECEIPT_ROWS)
        and offline.get("network_used") is False
    )


@dataclass(frozen=True)
class ServiceState:
    name: str
    enabled: bool
    state: str


@dataclass(frozen=True)
class Generation:
    name: str
    root_ref: str
    root: pathlib.Path
    service_environment: Mapping[str, str]
    unit_writable_paths: tuple[str, ...]
    services: tuple[ServiceState, ...]
    read_only: bool


class Rehearsal:
    """Small state transition model with an explicit writable-root guard."""

    def __init__(self, old: Generation, new: Generation) -> None:
        self.old = old
        self.new = new
        self.active_generation: str | None = None
        self.events: list[dict[str, object]] = []
        self.denied_operations: list[dict[str, str]] = []

    def _write_new_state(self) -> None:
        marker = self.new.root / "runtime" / "generation"
        require(marker.is_relative_to(self.new.root), "new state escaped its root")
        marker.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        marker.write_text("standalone\n", encoding="utf-8")
        os.chmod(marker, 0o640)
        self.events.append(
            {
                "generation": self.new.name,
                "operation": "write",
                "path": marker,
            }
        )

    def attempt_new_operation(self, operation: str, path: pathlib.Path) -> None:
        """Reject legacy-root operations before they can change the fixture."""
        if operation in FORBIDDEN_NEW_OPERATIONS or not path.is_relative_to(self.new.root):
            self.denied_operations.append(
                {"operation": operation, "path": str(path)}
            )
            raise Failure(
                f"new generation cannot {operation} outside {self.new.root}"
            )

    def transition(
        self,
        generation_name: str,
        *,
        offline: bool,
        failed_start: bool = False,
    ) -> bool:
        if generation_name == self.old.name:
            generation = self.old
        elif generation_name == self.new.name:
            generation = self.new
        else:
            raise Failure(f"unknown generation: {generation_name}")
        if failed_start:
            require(generation is self.new, "only the new generation may fail to start")
            self.events.append(
                {
                    "generation": self.new.name,
                    "operation": "startup-failed",
                    "path": self.new.root,
                    "offline": offline,
                }
            )
            return False

        if generation is self.old:
            require(generation.read_only, "old generation root is not read-only")
            require(
                all(not service.enabled and service.state == "stopped"
                    for service in generation.services),
                "old Gas City services are not all disabled and stopped",
            )
            self.events.append(
                {
                    "generation": generation.name,
                    "operation": "read",
                    "path": generation.root,
                    "offline": offline,
                }
            )
        else:
            self._write_new_state()

        self.active_generation = generation.name
        self.events.append(
            {
                "generation": generation.name,
                "operation": "activate",
                "path": generation.root,
                "offline": offline,
            }
        )
        return True


class RollbackAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        configured_root = os.environ.get("D2B_GASCITY_CHECK_RUN_ROOT")
        self.scratch = pathlib.Path(configured_root) if configured_root else ROOT / ".scratch"
        self.scratch.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(
            dir=self.scratch,
            prefix="rollback-",
        )
        self.base = pathlib.Path(self.temp.name)
        self.prototype = self.base / "prototype-root"
        self.standalone = self.base / "standalone-root"
        self.prototype.mkdir(mode=0o750)
        self.standalone.mkdir(mode=0o750)
        _write(
            self.prototype / "legacy-state.json",
            '{"state":"blocked-prototype","agents":0,"work":0}\n',
            0o640,
        )
        _write(self.prototype / "status.txt", "stopped\n", 0o640)
        _freeze_tree(self.prototype)
        _write(
            self.standalone / "bootstrap.json",
            '{"state":"empty","started":false}\n',
            0o640,
        )
        os.chmod(self.standalone, 0o750)
        self.manifest = self.base / "prototype.integrity.json"
        _write_integrity_manifest(self.prototype, self.manifest)
        self.prototype_before = _tree_snapshot(self.prototype)
        self.manifest_before = _file_state(self.manifest)
        self.old = Generation(
            name="old",
            root_ref=PROTOTYPE_ROOT_REF,
            root=self.prototype,
            service_environment={"GC_HOME": PROTOTYPE_ROOT_REF},
            unit_writable_paths=(),
            services=(
                ServiceState(
                    name="d2b-gascity.service",
                    enabled=False,
                    state="stopped",
                ),
            ),
            read_only=True,
        )
        self.new = Generation(
            name="new",
            root_ref=STANDALONE_ROOT_REF,
            root=self.standalone,
            service_environment={
                "GC_HOME": STANDALONE_ROOT_REF,
                "XDG_STATE_HOME": STANDALONE_ROOT_REF,
            },
            unit_writable_paths=(STANDALONE_ROOT_REF,),
            services=(
                ServiceState(
                    name="d2b-gascity.service",
                    enabled=True,
                    state="running",
                ),
            ),
            read_only=False,
        )
        self.rehearsal = Rehearsal(self.old, self.new)
        self.retained_closures = {
            "old": {
                "path": "<retained-old-closure>",
                "sha256": "<old-closure-sha256>",
                "retained": True,
            },
            "new": {
                "path": "<retained-new-closure>",
                "sha256": "<new-closure-sha256>",
                "retained": True,
            },
        }

    def tearDown(self) -> None:
        self.temp.cleanup()
        if not os.environ.get("D2B_GASCITY_CHECK_RUN_ROOT"):
            try:
                self.scratch.rmdir()
            except OSError:
                pass

    def _offline_start(self, generation: str) -> bool:
        closure = self.retained_closures[generation]
        require(closure["retained"] is True, f"{generation} closure was collected")
        require(closure["path"].startswith("<retained-"), "closure path was not redacted")
        return self.rehearsal.transition(generation, offline=True)

    def test_prototype_is_immutable_to_new_actions(self) -> None:
        before = _tree_snapshot(self.prototype)
        manifest_before = _file_state(self.manifest)
        self.assertTrue(_verify_integrity_manifest(self.prototype, self.manifest))
        for operation in sorted(FORBIDDEN_NEW_OPERATIONS):
            with self.subTest(operation=operation):
                with self.assertRaises(Failure):
                    self.rehearsal.attempt_new_operation(
                        operation,
                        self.prototype / "legacy-state.json",
                    )
        self.assertEqual(_tree_snapshot(self.prototype), before)
        self.assertEqual(_file_state(self.manifest), manifest_before)
        self.assertTrue(_verify_integrity_manifest(self.prototype, self.manifest))
        self.assertEqual(self.prototype_before, before)
        self.assertFalse(
            any(event["generation"] == "new" and event["path"] == self.prototype
                for event in self.rehearsal.events)
        )
        self.assertFalse(
            (self.standalone / "legacy-state.json").exists(),
            "prototype state was copied into the standalone root",
        )

    def test_old_generation_is_read_only_and_all_old_services_are_stopped(self) -> None:
        self.assertTrue(self.old.read_only)
        self.assertEqual(_tree_snapshot(self.prototype)["."]["mode"], "0o555")
        self.assertTrue(
            all(
                int(str(entry["mode"]), 8) & 0o222 == 0
                for entry in _tree_snapshot(self.prototype).values()
            )
        )
        self.assertTrue(
            all(not service.enabled and service.state == "stopped"
                for service in self.old.services)
        )
        self.assertTrue(self._offline_start("old"))
        self.assertEqual(self.rehearsal.active_generation, "old")
        self.assertEqual(_tree_snapshot(self.prototype), self.prototype_before)

    def test_new_generation_only_writes_standalone_root_without_legacy_paths(self) -> None:
        self.assertEqual(self.new.unit_writable_paths, (STANDALONE_ROOT_REF,))
        self.assertTrue(self.new.root_ref in self.new.service_environment.values())
        for value in self.new.service_environment.values():
            self.assertNotIn(PROTOTYPE_ROOT_REF, value)
            self.assertNotIn("prototype", value.lower())
        for path in self.new.unit_writable_paths:
            self.assertEqual(path, STANDALONE_ROOT_REF)
            self.assertNotIn("prototype", path.lower())
        self.assertTrue(self._offline_start("new"))
        writes = [
            event for event in self.rehearsal.events
            if event["operation"] == "write"
        ]
        self.assertTrue(writes)
        self.assertTrue(
            all(
                event["generation"] == "new"
                and pathlib.Path(event["path"]).is_relative_to(self.standalone)
                for event in writes
            )
        )
        self.assertEqual(_tree_snapshot(self.prototype), self.prototype_before)

    def test_old_new_old_new_preserves_state_and_mutation_scope(self) -> None:
        standalone_before = _tree_snapshot(self.standalone)
        self.assertTrue(self._offline_start("old"))
        self.assertTrue(self._offline_start("new"))
        standalone_after_first_new = _tree_snapshot(self.standalone)
        for relative, entry in standalone_before.items():
            self.assertEqual(standalone_after_first_new[relative], entry)
        self.assertTrue(self._offline_start("old"))
        self.assertTrue(self._offline_start("new"))
        self.assertEqual(_tree_snapshot(self.prototype), self.prototype_before)
        self.assertEqual(_file_state(self.manifest), self.manifest_before)
        self.assertTrue(_verify_integrity_manifest(self.prototype, self.manifest))
        self.assertEqual(_tree_snapshot(self.standalone), standalone_after_first_new)
        write_events = [
            event for event in self.rehearsal.events
            if event["operation"] == "write"
        ]
        self.assertTrue(write_events)
        self.assertTrue(
            all(
                event["generation"] == "new"
                and pathlib.Path(event["path"]).is_relative_to(self.standalone)
                for event in write_events
            )
        )
        self.assertFalse(
            any(
                event["operation"] in FORBIDDEN_NEW_OPERATIONS
                for event in self.rehearsal.events
            )
        )

    def test_failed_new_start_leaves_old_generation_usable(self) -> None:
        self.assertTrue(self._offline_start("old"))
        old_before = _tree_snapshot(self.prototype)
        manifest_before = _file_state(self.manifest)
        self.assertFalse(
            self.rehearsal.transition(
                "new",
                offline=True,
                failed_start=True,
            )
        )
        self.assertEqual(self.rehearsal.active_generation, "old")
        self.assertEqual(_tree_snapshot(self.prototype), old_before)
        self.assertEqual(_file_state(self.manifest), manifest_before)
        self.assertTrue(self._offline_start("old"))
        self.assertEqual(self.rehearsal.active_generation, "old")

    def test_retained_closures_prove_offline_rollback_without_network(self) -> None:
        self.assertTrue(self._offline_start("old"))
        self.assertTrue(self._offline_start("new"))
        self.assertTrue(self._offline_start("old"))
        self.assertTrue(self._offline_start("new"))
        self.assertTrue(
            all(closure["retained"] is True for closure in self.retained_closures.values())
        )
        self.assertTrue(
            all(
                event.get("offline") is True
                for event in self.rehearsal.events
                if event["operation"] in {"read", "activate"}
            )
        )
        self.assertFalse(any(event.get("network") is True for event in self.rehearsal.events))

    def test_receipt_schema_keeps_u12_ineligible_until_host_evidence_exists(self) -> None:
        receipt = _load_receipt()
        _validate_receipt(receipt)
        self.assertIs(receipt["host_generated"], False)
        self.assertIs(receipt["eligible_for_u12"], False)
        self.assertFalse(_eligible_for_u12(receipt))
        incomplete_host_receipt = copy.deepcopy(receipt)
        incomplete_host_receipt["host_generated"] = True
        incomplete_host_receipt["eligible_for_u12"] = True
        rows = incomplete_host_receipt["rows"]
        assert isinstance(rows, dict)
        rows["offline_rollback"]["status"] = "pending"
        self.assertFalse(_eligible_for_u12(incomplete_host_receipt))
        complete_host_receipt = copy.deepcopy(incomplete_host_receipt)
        complete_rows = complete_host_receipt["rows"]
        assert isinstance(complete_rows, dict)
        for row in complete_rows.values():
            assert isinstance(row, dict)
            row["status"] = "pass"
        complete_rows["offline_rollback"]["network_used"] = False
        self.assertTrue(_eligible_for_u12(complete_host_receipt))


if __name__ == "__main__":
    unittest.main(verbosity=2)
