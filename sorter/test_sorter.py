"""Grok 4.7 - SORTER-SEAT

Sorter checks against the shipped Base. Does not edit Base.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

from sorter import apply, order_round, plan

_BASE = Path(__file__).resolve().parents[1] / "base" / "base.py"
_spec = importlib.util.spec_from_file_location("agape_base", _BASE)
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
open_base = _base.open_base

_SHA = "0" * 64
_HELLO = (
    Path(__file__).resolve().parents[1]
    / "mod"
    / "ROUND0"
    / "packages"
    / "hello-bw"
    / "MANIFEST.json"
)
_HELLO_SHA = "f06effb9c5912625c5c07153663b35ad1fa9d0daf66458b8f40b370c7ee6e477"


def _enabled(*ids: str):
    core = open_base("box-b")
    for mod_id in ids:
        row = core.enable(mod_id, _SHA)
        if row["result"] != "enabled":
            raise AssertionError(row)
    return core


def _hello_submission() -> dict:
    raw = _HELLO.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != _HELLO_SHA:
        raise AssertionError(digest)
    return json.loads(raw.decode("utf-8"))


class PlanTests(unittest.TestCase):
    def test_keeps_enabled_order_when_unconstrained(self) -> None:
        result = plan(["c", "a", "b"])
        self.assertEqual(result["result"], "clear")
        self.assertEqual(result["ids"], ["c", "a", "b"])

    def test_before_moves_the_earlier_id_forward(self) -> None:
        result = plan(["a", "b", "c"], before=[("c", "a")])
        self.assertEqual(result["ids"], ["b", "c", "a"])

    def test_pair_conflict_blocks_the_list(self) -> None:
        result = plan(["a", "b"], conflicts=[("b", "a")])
        self.assertEqual(result["result"], "conflict")
        self.assertIsNone(result["ids"])
        self.assertEqual(result["conflicts"][0]["kind"], "pair")

    def test_cycle_blocks_the_list(self) -> None:
        result = plan(["a", "b"], before=[("a", "b"), ("b", "a")])
        self.assertEqual(result["result"], "conflict")
        self.assertEqual(result["conflicts"][0]["kind"], "cycle")

    def test_duplicate_enabled_id_is_a_conflict(self) -> None:
        result = plan(["a", "a"])
        self.assertEqual(result["result"], "conflict")
        self.assertEqual(result["conflicts"][0]["kind"], "duplicate")


class ApplyTests(unittest.TestCase):
    def test_set_order_accepts_a_clear_plan(self) -> None:
        core = _enabled("a", "b", "c")
        result = apply(core, before=[("c", "a")])
        self.assertTrue(result["applied"])
        self.assertEqual(core.list_order(), ["b", "c", "a"])
        self.assertEqual(result["receipt"]["result"], "enabled")
        self.assertEqual(result["receipt"]["action"], "set_order")

    def test_conflict_does_not_call_set_order(self) -> None:
        core = _enabled("a", "b")
        before = len(core.receipts())
        result = apply(core, conflicts=[("a", "b")])
        self.assertFalse(result["applied"])
        self.assertIsNone(result["receipt"])
        self.assertEqual(core.list_order(), ["a", "b"])
        self.assertEqual(len(core.receipts()), before)


class RoundTests(unittest.TestCase):
    def test_hello_bw_round_feeds_set_order(self) -> None:
        submission = _hello_submission()
        core = open_base("box-b")
        enabled = core.enable("hello-bw", _HELLO_SHA)
        self.assertEqual(enabled["result"], "enabled")
        result = order_round(core, [submission], round_id="0")
        self.assertEqual(result["result"], "clear")
        self.assertEqual(result["round_id"], "0")
        self.assertEqual(result["named_point"], "NP-20261026T170000Z")
        self.assertEqual(result["submissions"], ["hello-bw"])
        self.assertEqual(result["ids"], ["hello-bw"])
        self.assertTrue(result["applied"])
        self.assertEqual(core.list_order(), ["hello-bw"])
        self.assertEqual(result["receipt"]["action"], "set_order")
        self.assertEqual(result["receipt"]["result"], "enabled")

    def test_requires_loads_earlier_and_keeps_stable_ties(self) -> None:
        core = _enabled("b", "c", "a")
        submissions = [
            {"mod_id": "b", "requires": ["a"], "conflicts": []},
            {"mod_id": "c", "requires": [], "conflicts": []},
            {"mod_id": "a", "requires": [], "conflicts": []},
        ]
        result = order_round(core, submissions, round_id="0")
        self.assertEqual(result["ids"], ["c", "a", "b"])
        self.assertEqual(core.list_order(), ["c", "a", "b"])

    def test_declared_conflict_does_not_call_set_order(self) -> None:
        core = _enabled("a", "b")
        before = len(core.receipts())
        result = order_round(
            core,
            [{"mod_id": "a", "requires": [], "conflicts": ["b"]}],
            round_id="0",
        )
        self.assertEqual(result["result"], "conflict")
        self.assertFalse(result["applied"])
        self.assertIsNone(result["receipt"])
        self.assertEqual(result["conflicts"][0]["kind"], "pair")
        self.assertEqual(core.list_order(), ["a", "b"])
        self.assertEqual(len(core.receipts()), before)

    def test_missing_requirement_is_unknown(self) -> None:
        core = _enabled("b")
        before = len(core.receipts())
        result = order_round(
            core,
            [{"mod_id": "b", "requires": ["missing"], "conflicts": []}],
            round_id="0",
        )
        self.assertEqual(result["result"], "conflict")
        self.assertFalse(result["applied"])
        self.assertEqual(result["conflicts"][0]["kind"], "unknown")
        self.assertEqual(core.list_order(), ["b"])
        self.assertEqual(len(core.receipts()), before)

    def test_submission_not_enabled_is_a_conflict(self) -> None:
        core = open_base("box-b")
        before = len(core.receipts())
        result = order_round(core, [_hello_submission()], round_id="0")
        self.assertEqual(result["result"], "conflict")
        self.assertFalse(result["applied"])
        self.assertEqual(result["conflicts"][0]["kind"], "not_enabled")
        self.assertEqual(result["conflicts"][0]["id"], "hello-bw")
        self.assertEqual(core.list_order(), [])
        self.assertEqual(len(core.receipts()), before)

    def test_prior_enabled_mod_stays_when_the_submission_has_no_requires(self) -> None:
        core = _enabled("older")
        core.enable("hello-bw", _HELLO_SHA)
        result = order_round(core, [_hello_submission()], round_id="0")
        self.assertEqual(result["ids"], ["older", "hello-bw"])
        self.assertEqual(core.list_order(), ["older", "hello-bw"])


if __name__ == "__main__":
    unittest.main()
