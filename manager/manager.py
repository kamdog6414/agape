"""Muse Spark - MANAGER-SEAT

Agape Manager v1. Installs, enables and disables mods on a Base core,
and logs every change with a receipt. See MANAGER.md.

Built against: BASE-SEAT base/INTERFACE.md agape.base.v1 (Manager calls and
  the "v0 records" section; v0 enable/disable semantics unchanged).
  base.py read in full; enable/disable/set_order/list_order/receipts/
  note_laws are line-identical in behavior to v0. Round calls
  (open_round/submit/score) belong to Conformance, not Manager.
Mod reader: GPT Codex - MOD-SEAT MOD-FORMAT.md agape.mod.v0
  sha256 f3489924767d79337d4f8d6f224e11eb012215728abe4116935f5c250d101147
  (verified before use) via package.py verify_package
  sha256 f480d6141d075e719a12cb9a0b76da37993daf1d40e00128f45cc1bf7689c8a0
  (verified before use). Hashes are of the copies in this repository.
  Manager defines no package format of its own.
Named point: NP-20261026T170000Z (this file is in-window development).

Stdlib only. No network. No service control. No credential files.
Never imports or executes package payloads.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
from datetime import datetime, timezone
from pathlib import Path

VERSION = "agape.manager.v1"
ACCEPTED_BASE = ("agape.base.v0", "agape.base.v1")
NAMED_POINT = "NP-20261026T170000Z"

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load %s" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_base():
    """Load base.py from the sibling base/ directory, wherever this tree sits."""
    here = Path(__file__).resolve().parent
    base_py = here.parent / "base" / "base.py"
    mod = _load_module("agape_base", base_py)
    if getattr(mod, "VERSION", "") not in ACCEPTED_BASE:
        raise RuntimeError("base version not accepted: %r" % getattr(mod, "VERSION", ""))
    if getattr(mod, "NAMED_POINT", "") != NAMED_POINT:
        raise RuntimeError("base named point mismatch")
    return mod


def read_package(package_dir, expected_sha256: str, reader_path=None) -> dict:
    """Verify one mod package with MOD-SEAT's reader. Returns the reader dict.

    Default reader: <package_dir>/../../package.py per the MOD layout
    (ROUND0/packages/<id> next to ROUND0/package.py). Raises the reader's
    PackageError on any refusal. Never imports or executes payload code.
    """
    package_dir = Path(package_dir)
    if reader_path is None:
        reader_path = package_dir.parent.parent / "package.py"
    reader = _load_module("agape_mod_reader", Path(reader_path))
    info = reader.verify_package(str(package_dir), expected_sha256)
    with open(reader_path, "rb") as fh:
        reader_sha256 = hashlib.sha256(fh.read()).hexdigest()
    return {
        "mod_id": info["mod_id"],
        "version": info["version"],
        "manifest_sha256": info["manifest_sha256"],
        "entrypoint": info["entrypoint"],
        "requires": info["requires"],
        "conflicts": info["conflicts"],
        "file_count": info["file_count"],
        "payload_bytes": info["payload_bytes"],
        "reader": str(reader_path),
        "reader_sha256": reader_sha256,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Manager:
    """Install registry plus enable/disable on a Base core. Every change logged."""

    def __init__(self, box: str) -> None:
        self._base_mod = _load_base()
        self.core = self._base_mod.open_base(box)
        self.box = box
        self.base_version = self._base_mod.VERSION
        self._installed: dict[str, str] = {}
        self._log: list[dict] = []

    def _log_change(self, action: str, mod_id: str, sha, result: str) -> dict:
        row = {
            "action": action,
            "manifest_sha256": sha,
            "mod_id": mod_id,
            "result": result,
            "ts_utc": utc_now(),
        }
        self._log.append(row)
        return row

    def install(self, mod_id: str, manifest_sha256: str) -> dict:
        """Register one mod as installed from an already-trusted id+sha pair."""
        if not _ID.match(mod_id or ""):
            return self._log_change("install", mod_id or "", manifest_sha256, "refused")
        if not _SHA.fullmatch(manifest_sha256 or ""):
            return self._log_change("install", mod_id, manifest_sha256, "refused")
        if mod_id in self._installed:
            return self._log_change("install", mod_id, manifest_sha256, "refused")
        self._installed[mod_id] = manifest_sha256
        return self._log_change("install", mod_id, manifest_sha256, "installed")

    def install_from_package(self, package_dir, expected_sha256: str, reader_path=None) -> dict:
        """Verify a package against its external pin, then install its id+sha.

        Any reader refusal becomes a refused install row; nothing is registered.
        """
        try:
            info = read_package(package_dir, expected_sha256, reader_path)
        except Exception as exc:  # reader refused: malformed, pin, inventory, payload
            row = self._log_change("install", str(package_dir), expected_sha256, "refused")
            row["reason"] = "%s: %s" % (type(exc).__name__, exc)
            return row
        row = self.install(info["mod_id"], info["manifest_sha256"])
        row["package"] = str(package_dir)
        row["reader_sha256"] = info["reader_sha256"]
        return row

    def enable(self, mod_id: str) -> dict:
        """Enable one installed mod through the Base core. Returns the Base receipt."""
        sha = self._installed.get(mod_id)
        if sha is None:
            row = self._log_change("enable", mod_id, None, "refused")
            row["base_result"] = "not_installed"
            return row
        receipt = self.core.enable(mod_id, sha)
        row = self._log_change("enable", mod_id, sha, receipt["result"])
        row["base_result"] = receipt["result"]
        return row

    def disable(self, mod_id: str) -> dict:
        """Disable one mod through the Base core. Returns the Base receipt."""
        receipt = self.core.disable(mod_id)
        sha = self._installed.get(mod_id)
        row = self._log_change("disable", mod_id, sha, receipt["result"])
        row["base_result"] = receipt["result"]
        return row

    def installed(self) -> dict[str, str]:
        return dict(self._installed)

    def changes(self) -> list[dict]:
        """Every install/enable/disable call, in order. Append-only."""
        return list(self._log)


def open_manager(box: str) -> Manager:
    return Manager(box)
