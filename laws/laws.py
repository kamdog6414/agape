"""Muse Wonder - LAWS-SEAT

Agape Laws v1 - the first law predicates. See PREDICATES.md.
Base records the names of predicates that passed via core.note_laws(names).
Base does not evaluate laws; this module does.
"""

from __future__ import annotations

import hashlib
import os
import re

NAMED_POINT = "NP-20261026T170000Z"
# The genesis manifest sha256 of the real named point. AGAPE_GENESIS_SHA256
# overrides it so the public demo can run against a synthetic genesis.
NAMED_POINT_MANIFEST_SHA256 = os.environ.get(
    "AGAPE_GENESIS_SHA256",
    "e605b853d6eea415073da043a65d9f28fb8b715e669d4ece94b0c74bee88e7b7",
)

TEXT_EXTS = {
    ".py", ".md", ".txt", ".json", ".jsonl", ".toml", ".yaml", ".yml",
    ".cfg", ".ini", ".sh", ".ps1", ".js", ".ts", ".html", ".css",
}


def named_point_hash(manifest_path: str) -> bool:
    """True when the manifest at manifest_path hashes to the named-point pin."""
    try:
        digest = hashlib.sha256()
        with open(manifest_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest() == NAMED_POINT_MANIFEST_SHA256
    except OSError:
        return False


def _iter_files(root: str):
    if os.path.isfile(root):
        yield root
        return
    for base, _dirs, files in os.walk(root):
        for name in sorted(files):
            yield os.path.join(base, name)


def _read_text(path: str):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        return raw.decode("utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        return None


_SECRET_NAME = re.compile(
    r"(?i)(secret|token|credential|password|passwd|\.pem$|\.key$|\.env)"
)
_SECRET_BODY = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token"
        r"|client[_-]?secret|password)\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"
    ),
]


def secret_hits(root: str) -> list:
    """Paths that trip the secret scan. Values are never returned."""
    hits = []
    for path in _iter_files(root):
        if _SECRET_NAME.search(os.path.basename(path)):
            hits.append(path + " (name)")
            continue
        text = _read_text(path)
        if text is None:
            continue
        if any(rx.search(text) for rx in _SECRET_BODY):
            hits.append(path + " (content)")
    return hits


def no_secrets_in_mod(root: str) -> bool:
    return not secret_hits(root)


_NETWORK_BODY = [
    re.compile(
        r"(?m)^\s*(?:import|from)\s+(?:socket|urllib|requests"
        r"|http\.client|http\.server|websocket|websockets|ftplib"
        r"|smtplib|telnetlib|aiohttp|httpx)\b"
    ),
    re.compile(r"\bsocket\s*\.\s*socket\s*\("),
    re.compile(r"\b(?:urlopen|create_connection)\s*\("),
    re.compile(r"0\.0\.0\.0"),
    re.compile(r"(?i)\bfunnel\b"),
]


def network_hits(root: str) -> list:
    hits = []
    for path in _iter_files(root):
        if os.path.splitext(path)[1].lower() not in TEXT_EXTS:
            continue
        text = _read_text(path)
        if text is None:
            continue
        if any(rx.search(text) for rx in _NETWORK_BODY):
            hits.append(path)
    return hits


def no_network(root: str) -> bool:
    """Static scan: True when no network capability shows in text files."""
    return not network_hits(root)


_COLOR_BODY = [
    re.compile(r"\x1b\["),
    re.compile(r"(?i)\b(?:color|background|background-color"
               r"|border-color)\s*:\s*[^;}]+"),
    re.compile(r"(?i)\b(?:rgb|rgba|hsl|hsla)\s*\("),
]


def color_hits(root: str) -> list:
    hits = []
    for path in _iter_files(root):
        text = _read_text(path)
        if text is None:
            continue
        if any(rx.search(text) for rx in _COLOR_BODY):
            hits.append(path)
    return hits


def black_and_white(root: str) -> bool:
    """True when no machine-readable color encoding is present."""
    return not color_hits(root)


PREDICATES = (
    "named_point_hash",
    "no_secrets_in_mod",
    "no_network",
    "black_and_white",
)


def evaluate(mod_root: str, manifest_path: str) -> dict:
    return {
        "named_point_hash": named_point_hash(manifest_path),
        "no_secrets_in_mod": no_secrets_in_mod(mod_root),
        "no_network": no_network(mod_root),
        "black_and_white": black_and_white(mod_root),
    }


def passed_names(mod_root: str, manifest_path: str) -> list:
    """Names, in PREDICATES order, ready for core.note_laws(...)."""
    results = evaluate(mod_root, manifest_path)
    return [name for name in PREDICATES if results[name]]
