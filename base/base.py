"""Grok 4.7 - BASE-SEAT

Agape Base v1. The shared core. See INTERFACE.md.
v0 calls stay. Round receipts are added.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

VERSION = "agape.base.v1"
NAMED_POINT = "NP-20261026T170000Z"
SLOTS = {
    "mod": "GPT Codex - MOD-SEAT",
    "manager": "Muse Spark - MANAGER-SEAT",
    "sorter": "Grok 4.7 - SORTER-SEAT",
    "laws": "Muse Wonder - LAWS-SEAT",
}
_SHA = re.compile(r"^[0-9a-f]{64}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Base:
    def __init__(self, box: str) -> None:
        if not box or any(ch.isspace() for ch in box):
            raise ValueError("box")
        self.box = box
        self._order: list[str] = []
        self._sha: dict[str, str] = {}
        self._laws: list[str] = []
        self._receipts: list[dict] = []
        self._round_id: str | None = None
        self._round_sha: str | None = None
        self._submissions: list[dict] = []
        self._scores: list[dict] = []

    def _receipt(self, action: str, mod_id: str, manifest_sha256: str | None, result: str) -> dict:
        row = {
            "action": action,
            "manifest_sha256": manifest_sha256,
            "mod_id": mod_id,
            "result": result,
            "ts_utc": utc_now(),
        }
        self._receipts.append(row)
        return row

    def enable(self, mod_id: str, manifest_sha256: str) -> dict:
        if not mod_id or mod_id in self._sha or not _SHA.fullmatch(manifest_sha256 or ""):
            return self._receipt("enable", mod_id or "", manifest_sha256, "refused")
        self._sha[mod_id] = manifest_sha256
        self._order.append(mod_id)
        return self._receipt("enable", mod_id, manifest_sha256, "enabled")

    def disable(self, mod_id: str) -> dict:
        if mod_id not in self._sha:
            return self._receipt("disable", mod_id, None, "refused")
        digest = self._sha.pop(mod_id)
        self._order = [item for item in self._order if item != mod_id]
        return self._receipt("disable", mod_id, digest, "disabled")

    def set_order(self, ids: list[str]) -> dict:
        if sorted(ids) != sorted(self._order) or len(ids) != len(set(ids)):
            return self._receipt("set_order", ",".join(ids), None, "refused")
        self._order = list(ids)
        return self._receipt("set_order", ",".join(ids), None, "enabled")

    def list_order(self) -> list[str]:
        return list(self._order)

    def receipts(self) -> list[dict]:
        return list(self._receipts)

    def open_round(self, round_id: str, named_point_sha256: str) -> dict:
        if self._round_id or not round_id or " " in round_id or not _SHA.fullmatch(named_point_sha256 or ""):
            return self._receipt("open_round", round_id or "", named_point_sha256, "refused")
        self._round_id = round_id
        self._round_sha = named_point_sha256
        row = self._receipt("open_round", round_id, named_point_sha256, "enabled")
        row["round_id"] = round_id
        row["named_point"] = NAMED_POINT
        return row

    def submit(self, mod_id: str, manifest_sha256: str) -> dict:
        if not self._round_id or not mod_id or not _SHA.fullmatch(manifest_sha256 or ""):
            return self._receipt("submit", mod_id or "", manifest_sha256, "refused")
        if any(item["mod_id"] == mod_id for item in self._submissions):
            return self._receipt("submit", mod_id, manifest_sha256, "refused")
        self._submissions.append({"manifest_sha256": manifest_sha256, "mod_id": mod_id, "round_id": self._round_id})
        row = self._receipt("submit", mod_id, manifest_sha256, "enabled")
        row["round_id"] = self._round_id
        return row

    def score(self, mod_id: str, law: str, result: str, evidence_sha256: str) -> dict:
        known = any(item["mod_id"] == mod_id for item in self._submissions)
        clean = law and " " not in law and result in {"PASS", "FAIL"} and _SHA.fullmatch(evidence_sha256 or "") and known
        if not self._round_id or not clean:
            return self._receipt("score", mod_id or "", evidence_sha256, "refused")
        self._scores.append(
            {
                "evidence_sha256": evidence_sha256,
                "law": law,
                "mod_id": mod_id,
                "result": result,
                "round_id": self._round_id,
            }
        )
        row = self._receipt("score", mod_id, evidence_sha256, result)
        row["law"] = law
        row["round_id"] = self._round_id
        return row

    def round_state(self) -> dict:
        return {
            "named_point": NAMED_POINT,
            "named_point_sha256": self._round_sha,
            "round_id": self._round_id,
            "scores": list(self._scores),
            "submissions": list(self._submissions),
        }

    def note_laws(self, names: list[str]) -> dict:
        clean = [name for name in names if name and " " not in name]
        if len(clean) != len(names):
            return self._receipt("note_laws", "", None, "refused")
        self._laws = list(clean)
        return self._receipt("note_laws", ",".join(clean), None, "enabled")

    def probe(self) -> dict:
        return {
            "box": self.box,
            "laws": list(self._laws),
            "named_point": NAMED_POINT,
            "order": list(self._order),
            "receipts": len(self._receipts),
            "round_id": self._round_id,
            "scores": len(self._scores),
            "submissions": len(self._submissions),
            "slots": dict(SLOTS),
            "version": VERSION,
        }


def open_base(box: str) -> Base:
    return Base(box)


def probe_json(box: str) -> str:
    return json.dumps(open_base(box).probe(), separators=(",", ":"), sort_keys=True)
