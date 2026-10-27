"""Muse Wonder - LAWS-SEAT

Agape Laws v2 - the named-point chain.

Built on the founder's ruling on the L-11 question (2026-10-26):
check each round's own named point and confirm the chain leads
back to this morning's point.

v1 pinned the genesis manifest as a constant: any round pointing
laws at a newer point would FAIL forever. v2 keeps genesis as
the root of trust - GENESIS_MANIFEST_SHA256 never moves - but
evaluates the point a round actually presents: hash the
presented manifest, then walk its parent links to genesis.

The parent link is the convention the genesis manifest itself
uses: the "supersedes" block names the prior manifest by its
file sha256. "parent_manifest_sha256" is accepted as an alias.

  verify_point(manifest_path, search_dirs=None) -> dict
      {point, manifest_sha256, chain, depth, verdict, reason}
      chain lists manifest sha256s from the presented point
      down to genesis. depth 0 means the presented point IS
      genesis.
  named_point_hash(manifest_path, search_dirs=None) -> bool
      v2 meaning: the presented point chains to genesis.
  evaluate(mod_root, manifest_path, search_dirs=None)
  passed_names(mod_root, manifest_path, search_dirs=None)

The three content predicates are v1's, imported unchanged.
laws.py v1 stays the Round 0 scorer of record; v2 governs
Round 1 and later. Parent manifests are found in the presented
manifest's own folder, its parent folder, that folder's
immediate subfolders (the folder-per-point layout), plus any
search_dirs given. The walk is cycle-safe and depth-capped.
"""

from __future__ import annotations

import hashlib
import json
import os
import re

import laws as _v1

GENESIS_POINT = "NP-20261026T170000Z"
# Real genesis pin; AGAPE_GENESIS_SHA256 overrides it (public demo only).
GENESIS_MANIFEST_SHA256 = os.environ.get(
    "AGAPE_GENESIS_SHA256",
    "e605b853d6eea415073da043a65d9f28fb8b715e669d4ece94b0c74bee88e7b7",
)
MAX_DEPTH = 64
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Content predicates: v1's, unchanged.
secret_hits = _v1.secret_hits
network_hits = _v1.network_hits
color_hits = _v1.color_hits
no_secrets_in_mod = _v1.no_secrets_in_mod
no_network = _v1.no_network
black_and_white = _v1.black_and_white


def _file_sha256(path: str):
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _load_json(path: str):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _parent_sha(manifest) -> str | None:
    if not isinstance(manifest, dict):
        return None
    sup = manifest.get("supersedes")
    if isinstance(sup, dict):
        sha = sup.get("sha256")
        if isinstance(sha, str) and _HEX64.match(sha):
            return sha
    sha = manifest.get("parent_manifest_sha256")
    if isinstance(sha, str) and _HEX64.match(sha):
        return sha
    return None


def _candidate_manifests(manifest_path: str, search_dirs) -> list:
    roots = []
    here = os.path.dirname(os.path.abspath(manifest_path))
    roots.append(here)
    parent = os.path.dirname(here)
    roots.append(parent)
    for extra in search_dirs or []:
        roots.append(os.path.abspath(extra))
    found = []
    seen = set()
    for root in roots:
        spots = [root]
        try:
            for name in sorted(os.listdir(root)):
                sub = os.path.join(root, name)
                if os.path.isdir(sub):
                    spots.append(sub)
        except OSError:
            pass
        for spot in spots:
            cand = os.path.join(spot, "MANIFEST.json")
            if cand not in seen and os.path.isfile(cand):
                seen.add(cand)
                found.append(cand)
    if os.path.isfile(manifest_path):
        found.append(manifest_path)
    return found


def _index_points(manifest_path: str, search_dirs) -> dict:
    index = {}
    for cand in _candidate_manifests(manifest_path, search_dirs):
        sha = _file_sha256(cand)
        if sha and sha not in index:
            index[sha] = cand
    return index


def verify_point(manifest_path: str, search_dirs=None) -> dict:
    """Walk the presented point's parent links to genesis."""
    result = {
        "point": None,
        "manifest_sha256": _file_sha256(manifest_path),
        "chain": [],
        "depth": 0,
        "verdict": False,
        "reason": "",
    }
    if result["manifest_sha256"] is None:
        result["reason"] = "manifest unreadable"
        return result
    data = _load_json(manifest_path)
    if isinstance(data, dict):
        result["point"] = data.get("name")
    index = _index_points(manifest_path, search_dirs)
    current_path = manifest_path
    current_sha = result["manifest_sha256"]
    visited = set()
    while True:
        result["chain"].append(current_sha)
        if current_sha == GENESIS_MANIFEST_SHA256:
            result["verdict"] = True
            result["reason"] = ("genesis" if result["depth"] == 0
                                else "chained to genesis")
            return result
        if current_sha in visited:
            result["reason"] = "cycle in parent links"
            return result
        visited.add(current_sha)
        if result["depth"] >= MAX_DEPTH:
            result["reason"] = "depth exceeded"
            return result
        manifest = _load_json(current_path)
        parent_sha = _parent_sha(manifest)
        if parent_sha is None:
            result["reason"] = "no parent link"
            return result
        parent_path = index.get(parent_sha)
        if parent_path is None:
            result["reason"] = "parent manifest not found"
            return result
        current_path = parent_path
        current_sha = parent_sha
        result["depth"] += 1


def named_point_hash(manifest_path: str, search_dirs=None) -> bool:
    """v2: True when the presented point chains to genesis."""
    return verify_point(manifest_path, search_dirs)["verdict"]


PREDICATES = _v1.PREDICATES


def evaluate(mod_root: str, manifest_path: str, search_dirs=None) -> dict:
    return {
        "named_point_hash": named_point_hash(manifest_path, search_dirs),
        "no_secrets_in_mod": _v1.no_secrets_in_mod(mod_root),
        "no_network": _v1.no_network(mod_root),
        "black_and_white": _v1.black_and_white(mod_root),
    }


def passed_names(mod_root: str, manifest_path: str, search_dirs=None):
    results = evaluate(mod_root, manifest_path, search_dirs)
    return [name for name in PREDICATES if results[name]]
