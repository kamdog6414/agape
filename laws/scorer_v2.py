"""Muse Wonder - LAWS-SEAT

Agape Laws scorer v2 - Round 1 and later.

Same receipt shape as scorer.py, on laws_v2: the named-point
law now verifies the round's own point and its chain to
genesis, and the receipt carries the full point_verification
(point, manifest sha256, chain, depth, verdict, reason).

Run: python3 scorer_v2.py <mod_root> <manifest_path> <out_dir>
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

import laws_v2 as laws

SEAT = "Muse Wonder - LAWS-SEAT"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: str):
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _walk(root: str):
    if os.path.isfile(root):
        yield root
        return
    for base, _dirs, files in os.walk(root):
        for name in sorted(files):
            yield os.path.join(base, name)


def build_evidence(mod_root: str, manifest_path: str) -> str:
    lines = []
    lines.append("seat: " + SEAT)
    lines.append("mod_root: " + os.path.abspath(mod_root))
    lines.append("manifest_path: " + os.path.abspath(manifest_path))
    lines.append("manifest_sha256: "
                 + (_sha256_file(manifest_path) or "UNREADABLE"))
    lines.append("point_verification: "
                 + json.dumps(laws.verify_point(manifest_path),
                              sort_keys=True))
    lines.append("files:")
    for path in _walk(mod_root):
        lines.append("  " + (_sha256_file(path) or "UNREADABLE")
                     + "  " + path)
    lines.append("secret_hits: "
                 + json.dumps(laws.secret_hits(mod_root)))
    lines.append("network_hits: "
                 + json.dumps(laws.network_hits(mod_root)))
    lines.append("color_hits: "
                 + json.dumps(laws.color_hits(mod_root)))
    return "\n".join(lines) + "\n"


def score_mod(mod_root: str, manifest_path: str, out_dir: str):
    """Score one mod under v2. Returns (receipt_path, receipt)."""
    os.makedirs(out_dir, exist_ok=True)
    mod_name = os.path.basename(os.path.abspath(mod_root))
    evidence_path = os.path.join(out_dir, mod_name + "-evidence.txt")
    with open(evidence_path, "w", encoding="utf-8") as fh:
        fh.write(build_evidence(mod_root, manifest_path))
    evidence_sha = _sha256_file(evidence_path)
    point_check = laws.verify_point(manifest_path)
    results = laws.evaluate(mod_root, manifest_path)
    entries = []
    for name in laws.PREDICATES:
        if name == "named_point_hash":
            ev_path = os.path.abspath(manifest_path)
            ev_sha = _sha256_file(manifest_path) or "UNREADABLE"
        else:
            ev_path = os.path.abspath(evidence_path)
            ev_sha = evidence_sha
        entries.append({
            "name": name,
            "verdict": "PASS" if results[name] else "FAIL",
            "evidence_path": ev_path,
            "evidence_sha256": ev_sha,
        })
    receipt = {
        "seat": SEAT,
        "utc": _utc(),
        "point": point_check.get("point"),
        "point_verification": point_check,
        "mod_root": os.path.abspath(mod_root),
        "laws": entries,
        "overall": "PASS" if all(results[n] for n in laws.PREDICATES)
                   else "FAIL",
        "scorer_sha256": _sha256_file(os.path.abspath(__file__)),
    }
    receipt_path = os.path.join(out_dir, mod_name + "-score.json")
    with open(receipt_path, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return receipt_path, receipt


if __name__ == "__main__":
    import sys
    path, receipt = score_mod(sys.argv[1], sys.argv[2], sys.argv[3])
    print(path)
    print(json.dumps(receipt, indent=2, sort_keys=True))
