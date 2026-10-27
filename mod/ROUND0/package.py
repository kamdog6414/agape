"""GPT Codex - MOD-SEAT

Read-only agape.mod.v0 package reader. No imports or execution of payload code.
The external pin is mandatory. See MOD-FORMAT.md for the exact contract.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

HEADER = "GPT Codex - MOD-SEAT"
NAMED_POINT = "NP-20261026T170000Z"
ANCHOR = datetime.fromisoformat("2026-10-26T17:00:00.381572+00:00")
BASE = {
    "version": "agape.base.v0",
    "interface_sha256": "a40e530a26d92b749c7f79c54eb1b4cd7bce04f7942e9a303733a1e402e6b9b0",
    "manifest_sha256": "10ba805c736495ede2469da1308590f6500ef62427145d5d64f252b64b6a2c37",
}
RUNTIME = {
    "language": "python3", "dependencies": "stdlib", "network": False,
    "filesystem": "none", "processes": False,
}
FIELDS = {
    "header", "schema", "mod_id", "version", "named_point", "created_utc",
    "base", "entrypoint", "runtime", "inputs", "outputs", "requires",
    "conflicts", "files",
}
SHA = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z\Z")
COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}
CREDENTIAL_WORDS = {
    "key", "keys", "token", "tokens", "secret", "secrets", "auth",
    "authentication", "credential", "credentials", "password", "passwords",
}
MAX_MANIFEST = 65536
MAX_FILE = 1048576
MAX_TOTAL = 8388608


class PackageError(ValueError):
    """A package is refused; no payload has been executed."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise PackageError(reason)


def _object(value: object, fields: set[str], name: str) -> dict:
    _require(type(value) is dict and set(value) == fields, name + ": fields")
    return value


def _identifier(value: object) -> bool:
    return type(value) is str and len(value) <= 80 and IDENTIFIER.fullmatch(value) is not None


def _sha(value: object) -> bool:
    return type(value) is str and SHA.fullmatch(value) is not None


def _credential(component: str) -> bool:
    name = component.lower()
    if name in {".env", "id_rsa", "id_ed25519"}:
        return True
    if Path(name).suffix in {".pem", ".key", ".p12", ".pfx"}:
        return True
    return bool(set(re.split(r"[._-]", name)) & CREDENTIAL_WORDS)


def _path(value: object) -> str:
    _require(type(value) is str and len(value) <= 240, "payload path: length/type")
    parts = value.split("/")
    _require(len(parts) >= 2 and parts[0] == "payload", "payload path: prefix")
    for part in parts:
        _require(COMPONENT.fullmatch(part) is not None and not part.endswith("."), "payload path: component")
        _require(part.split(".")[0].lower() not in RESERVED, "payload path: reserved name")
        _require(not _credential(part), "payload path: credential filename refused before read")
    return value


def _pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, "manifest: duplicate JSON key")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise PackageError("manifest: non-finite JSON number")


def _ids(value: object, name: str, *, ordered: bool, nonempty: bool = False) -> list:
    _require(type(value) is list, name + ": array")
    _require((1 if nonempty else 0) <= len(value) <= (16 if nonempty else 64), name + ": count")
    _require(all(_identifier(item) for item in value), name + ": identifier")
    _require(len(value) == len(set(value)), name + ": duplicates")
    if ordered:
        _require(value == sorted(value), name + ": sort order")
    return value


def _stat(path: Path) -> os.stat_result:
    info = path.lstat()
    _require(not stat.S_ISLNK(info.st_mode), "inventory: links refused")
    _require(not (getattr(info, "st_file_attributes", 0) & 1024), "inventory: reparse point refused")
    _require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), "inventory: special file refused")
    if stat.S_ISREG(info.st_mode):
        _require(info.st_nlink == 1, "inventory: hardlinks refused")
    return info


def _read(path: Path, limit: int) -> bytes:
    before = _stat(path)
    _require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, "file: type or size limit")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    after = _stat(path)
    _require(len(data) <= limit, "file: read size limit")
    fingerprint = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink)
    _require(fingerprint(before) == fingerprint(after), "file: changed during verification")
    return data


def _metadata(raw: bytes) -> dict:
    try:
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except PackageError:
        raise
    except (ValueError, RecursionError) as exc:
        raise PackageError("manifest: invalid UTF-8 JSON") from exc
    m = _object(manifest, FIELDS, "manifest")
    _require(type(m["header"]) is str and 1 <= len(m["header"]) <= 120, "header: length/type")
    _require(m["schema"] == "agape.mod.v0", "schema: unsupported")
    _require(_identifier(m["mod_id"]), "mod_id: invalid")
    _require(type(m["version"]) is str and len(m["version"]) <= 80 and VERSION.fullmatch(m["version"]) is not None, "version: invalid")
    _require(m["named_point"] == NAMED_POINT, "named_point: mismatch")
    ts = m["created_utc"]
    _require(type(ts) is str and UTC.fullmatch(ts) is not None, "created_utc: UTC required")
    try:
        created = datetime.fromisoformat(ts[:-1] + "+00:00")
    except ValueError as exc:
        raise PackageError("created_utc: invalid date") from exc
    _require(created > ANCHOR, "created_utc: not after named point")
    _require(type(m["base"]) is dict and m["base"] == BASE, "base: unsupported contract/pins")
    runtime = _object(m["runtime"], set(RUNTIME), "runtime")
    _require(runtime == RUNTIME and runtime["network"] is False and runtime["processes"] is False, "runtime: unsupported profile")
    entry = _object(m["entrypoint"], {"path", "callable", "protocol"}, "entrypoint")
    _path(entry["path"])
    _require(entry["path"].endswith(".py") and entry["callable"] == "run" and entry["protocol"] == "agape.mod.call.v0", "entrypoint: unsupported protocol")
    _ids(m["inputs"], "inputs", ordered=False, nonempty=True)
    _ids(m["outputs"], "outputs", ordered=False, nonempty=True)
    for name in ("requires", "conflicts"):
        ids = _ids(m[name], name, ordered=True)
        _require(m["mod_id"] not in ids, name + ": self reference")
    files = m["files"]
    _require(type(files) is list and 1 <= len(files) <= 64, "files: count/type")
    paths = []
    folded = {}
    total = 0
    for item in files:
        row = _object(item, {"path", "bytes", "sha256"}, "file")
        path = _path(row["path"])
        paths.append(path)
        _require(type(row["bytes"]) is int and 0 <= row["bytes"] <= MAX_FILE, "file: bytes limit/type")
        _require(_sha(row["sha256"]), "file: sha256")
        total += row["bytes"]
        parts = path.split("/")
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            _require(folded.get(prefix.casefold(), prefix) == prefix, "files: case collision")
            folded[prefix.casefold()] = prefix
    _require(len(paths) == len(set(paths)) and paths == sorted(paths), "files: duplicates or sort order")
    _require(total <= MAX_TOTAL, "files: total size limit")
    _require(entry["path"] in paths, "entrypoint: not listed")
    # A declared regular file must not also be an ancestor directory.
    _require(not any(other.startswith(path + "/") for path in paths for other in paths), "files: file/directory conflict")
    return m


def verify_package(package_dir: str | Path, expected_sha256: str) -> dict:
    """Validate immutable local bytes; never import or execute package payloads."""
    _require(_sha(expected_sha256), "external manifest pin: 64 lowercase hex required")
    try:
        root = Path(package_dir).absolute()
        root_info = _stat(root)
        _require(stat.S_ISDIR(root_info.st_mode), "package root: directory required")
        raw = _read(root / "MANIFEST.json", MAX_MANIFEST)
        pin = hashlib.sha256(raw).hexdigest()
        _require(pin == expected_sha256, "manifest: external SHA256 pin mismatch")
        manifest = _metadata(raw)
        declared = {row["path"]: row for row in manifest["files"]}
        expected_dirs = {"/".join(path.split("/")[:i]) for path in declared for i in range(1, len(path.split("/")))}
        actual = set()
        actual_dirs = set()
        pending = [root]
        count = 0
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    count += 1
                    _require(count <= 256, "inventory: entry limit")
                    path = Path(entry.path)
                    relative = path.relative_to(root).as_posix()
                    info = _stat(path)
                    _require(info.st_dev == root_info.st_dev, "inventory: nested filesystem refused")
                    if stat.S_ISDIR(info.st_mode):
                        _require(relative in expected_dirs, "inventory: unexpected directory")
                        actual_dirs.add(relative)
                        pending.append(path)
                    else:
                        _require(relative == "MANIFEST.json" or relative in declared, "inventory: unlisted file")
                        actual.add(relative)
        _require(actual == {"MANIFEST.json", *declared}, "inventory: missing payload")
        _require(actual_dirs == expected_dirs, "inventory: missing directory")
        total = 0
        for path, row in declared.items():
            data = _read(root / path, MAX_FILE)
            _require(len(data) == row["bytes"], "payload: size mismatch")
            _require(hashlib.sha256(data).hexdigest() == row["sha256"], "payload: SHA256 mismatch")
            total += len(data)
        return {
            "mod_id": manifest["mod_id"], "version": manifest["version"],
            "manifest_sha256": pin, "entrypoint": dict(manifest["entrypoint"]),
            "requires": list(manifest["requires"]), "conflicts": list(manifest["conflicts"]),
            "file_count": len(declared), "payload_bytes": total,
        }
    except OSError as exc:
        raise PackageError("package: filesystem read refused (" + type(exc).__name__ + ")") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("package")
    verify.add_argument("--sha256", required=True)
    args = parser.parse_args()
    try:
        result = verify_package(args.package, args.sha256)
    except PackageError as exc:
        print(json.dumps({"header": HEADER, "status": "failed", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"header": HEADER, "status": "delivered", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
