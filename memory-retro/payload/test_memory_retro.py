"""Grok Bot - ROUND-SEAT

memory-retro v0 tests: exact values on planted good fixtures, and one falsifier
per metric (a planted fault must move exactly its metric). Stdlib unittest.
"""

import copy
import json
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures  # noqa: E402
import memory_retro as mr  # noqa: E402


def score(events):
    return mr.run({"schema": mr.REQ, "events": copy.deepcopy(events)})


def view(r):
    mc, cu, oa = r["memory_continuity"], r["context_usage"], r["operational_awareness"]
    chain = mc["chain_integrity"].get("chain/T|c", {})
    return {
        "provenance": mc["hash_provenance"]["counts"],
        "abbr_assistant": mc["abbreviation_fidelity"]["assistant"]["counts"],
        "binding": mc["binding_consistency"]["counts"],
        "compaction": mc["compaction_recall"],
        "chain_c": {k: chain.get(k) for k in ("records", "links_ok", "links_broken", "seq_gaps", "genesis_ok")},
        "cross_board": mc["cross_board_identity"],
        "usage_total": cu["total"],
        "reasks": {k: cu["reasks"][k] for k in ("user_asks", "repeat_within_session", "repeat_from_prior_session")},
        "rederivations": {k: cu["rederivations"][k] for k in
                          ("tool_hash_mentions", "already_seen_same_session", "already_seen_prior_session")},
        "positive": {k: oa["assistant_claims"]["by_class"]["positive"][k] for k in
                     ("claims", "backed_strict", "backed_any", "contradicted", "unbacked")},
        "posts": {k: oa["board_posts"][k] for k in ("posts", "with_status", "status_delivered_like",
                                                    "delivered_with_evidence_hash", "delivered_without_evidence")},
        "post_sidecar": oa["board_posts"]["sidecar"],
        "report_sidecar": oa["desk_reports"]["sidecar"],
        "register_pass": oa["register"]["by_verdict"].get("PASS"),
        "fails_closed": oa["fails_ledger"].get("CLOSED"),
        "first_utc": r["coverage"]["first_utc"],
        "last_utc": r["coverage"]["last_utc"],
        "dropped": r["coverage"]["privacy_dropped"],
    }


def get(v, path):
    a, b = path.split(".")
    return v[a][b]


class GoodFixture(unittest.TestCase):
    def test_exact_values(self):
        v = view(score(fixtures.good()))
        for k, want in fixtures.GOOD_EXPECTED.items():
            self.assertEqual(v[k], want, k)

    def test_result_shape(self):
        r = score(fixtures.good())
        self.assertEqual((r["schema"], r["status"], r["header"]), (mr.RES, "delivered", mr.HEADER))
        self.assertEqual(r["memory_continuity"]["hash_provenance"]["sourced"], {"num": 3, "den": 3, "rate": "1.0000"})

    def test_order_independent(self):
        ev = fixtures.good()
        base = json.dumps(score(ev), sort_keys=True)
        rnd = random.Random(20261027)
        for _ in range(5):
            rnd.shuffle(ev)
            self.assertEqual(json.dumps(score(ev), sort_keys=True), base)

    def test_json_round_trip_ascii(self):
        s = json.dumps(score(fixtures.good()), ensure_ascii=True, sort_keys=True, allow_nan=False)
        self.assertEqual(json.loads(s), score(fixtures.good()))


class Falsifiers(unittest.TestCase):
    """Each planted fault must move exactly its targeted values; all else stays as GOOD."""

    def test_each_defect_detected(self):
        good = view(score(fixtures.good()))
        self.assertEqual(len(fixtures.DEFECTS), 14)
        for name, (extra, expect) in sorted(fixtures.DEFECTS.items()):
            with self.subTest(defect=name):
                bad = view(score(fixtures.good() + extra))
                moved = 0
                for path, want in expect.items():
                    self.assertEqual(get(bad, path), want, path)
                    moved += get(good, path) != want
                self.assertGreater(moved, 0, "defect %s moved nothing" % name)

    def test_defects_do_not_leak_into_other_targets(self):
        good = view(score(fixtures.good()))
        guarded = ["provenance.UNSOURCED", "abbr_assistant.CORRUPT", "binding.STALE", "positive.unbacked",
                   "positive.contradicted", "reasks.repeat_from_prior_session", "reasks.repeat_within_session",
                   "rederivations.already_seen_prior_session", "chain_c.links_broken",
                   "cross_board.multi_board_divergent", "report_sidecar.mismatch", "register_pass.none"]
        for name, (extra, expect) in sorted(fixtures.DEFECTS.items()):
            bad = view(score(fixtures.good() + extra))
            for path in guarded:
                if path not in expect:
                    with self.subTest(defect=name, path=path):
                        self.assertEqual(get(bad, path), get(good, path))

    def test_all_defects_together(self):
        extra = []
        for name, (ev, _) in sorted(fixtures.DEFECTS.items()):
            for e in ev:
                if e.get("sess") == "S3":
                    e = dict(e, sess="S3-" + name)
                extra.append(e)
        v = view(score(fixtures.good() + extra))
        self.assertEqual(v["provenance"]["UNSOURCED"], 1)
        self.assertEqual(v["abbr_assistant"]["CORRUPT"], 1)
        self.assertEqual(v["binding"]["STALE"], 1)
        self.assertEqual(v["positive"]["unbacked"], 1)
        self.assertEqual(v["positive"]["contradicted"], 1)
        self.assertEqual(v["chain_c"]["links_broken"], 1)
        self.assertEqual(v["register_pass"]["none"], 1)


class Units(unittest.TestCase):
    def test_norm_t(self):
        self.assertEqual(mr.norm_t("2026-10-26T00:14:11-07:00"), "2026-10-26T07:14:11.000000Z")
        self.assertEqual(mr.norm_t("2026-08-12T17:55:07.3091234Z"), "2026-08-12T17:55:07.309123Z")
        self.assertEqual(mr.norm_t("2026-10-27T03:15"), "2026-10-27T03:15:00.000000Z")
        self.assertEqual(mr.norm_t("not a time"), "")
        self.assertEqual(mr.norm_t(None), "")

    def test_ratio(self):
        self.assertEqual(mr.ratio(1, 3), {"num": 1, "den": 3, "rate": "0.3333"})
        self.assertEqual(mr.ratio(0, 0), {"num": 0, "den": 0, "rate": "n/a"})

    def test_short_prefix_not_corrupt(self):
        ev = fixtures.good() + [fixtures._s3(1, "assistant", "2026-08-03T00:00:01Z", full=[],
                                             abbr=[["1a1a1a", "ffff"]], bind=[], claims=[])]
        self.assertEqual(view(score(ev))["abbr_assistant"]["CORRUPT"], 0)

    def test_request_validation(self):
        for bad in ([], {"schema": mr.REQ}, {"schema": "x", "events": []},
                    {"schema": mr.REQ, "events": {}}, {"schema": mr.REQ, "events": [], "extra": 1},
                    {"schema": mr.REQ, "events": [{"t": "x"}]}):
            with self.assertRaises(ValueError):
                mr.run(bad)

    def test_empty(self):
        r = mr.run({"schema": mr.REQ, "events": [], "not_run": ["b", "a"]})
        self.assertEqual(r["coverage"]["not_run"], ["a", "b"])
        self.assertEqual(r["coverage"]["events"], 0)

    def test_payload_is_pure(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "memory_retro.py"), encoding="utf-8") as fh:
            src = fh.read()
        for word in ("import os", "import socket", "import subprocess", "urllib", "open(", "import http"):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
