"""Grok Bot - ROUND-SEAT

Planted fixtures for memory-retro v0. GOOD is a clean corpus with exact known
metric values. DEFECTS are single planted faults; each one, added to GOOD,
must move exactly the metric it targets by a known amount.
"""

H1 = "1a" * 32
H2 = "2b" * 32
H9 = "9f" * 32
X1, X2, X3 = "c1" * 32, "c2" * 32, "c3" * 32
F1 = "f1" * 32
P1, P2 = "d1" * 32, "d2" * 32
G = "0" * 64


def ev(kind, t, **kw):
    d = {"kind": kind, "t": t}
    d.update(kw)
    return d


def _s(sess, i, kind, t, **kw):
    return ev(kind, t, src="codex/T", sess=sess, i=i, **kw)


def good():
    return [
        _s("S1", 0, "session", "2026-08-01T00:00:00Z"),
        _s("S1", 1, "user", "2026-08-01T00:00:01Z", fp="f000000000000001", full=[], abbr=[], bind=[]),
        _s("S1", 2, "tool", "2026-08-01T00:00:02Z", full=[H1], bind=[["a.txt", H1]], strong=True, weak=False, fail=False),
        _s("S1", 3, "assistant", "2026-08-01T00:00:03Z", full=[H1], abbr=[["1a1a1a1a", "1a1a"]],
           bind=[["a.txt", H1]], claims=["PASS"]),
        _s("S1", 4, "usage", "2026-08-01T00:00:04Z", total=1000, input=800, cached=600, output=200,
           last_input=500, window=1000),
        _s("S1", 5, "compaction", "2026-08-01T00:00:05Z"),
        _s("S1", 6, "assistant", "2026-08-01T00:00:06Z", full=[H1], abbr=[], bind=[], claims=[]),
        _s("S1", 7, "usage", "2026-08-01T00:00:07Z", total=2000, input=1600, cached=1200, output=400,
           last_input=950, window=1000),
        _s("S2", 0, "session", "2026-08-02T00:00:00Z"),
        _s("S2", 1, "user", "2026-08-02T00:00:01Z", fp="f000000000000002", full=[], abbr=[], bind=[]),
        _s("S2", 2, "tool", "2026-08-02T00:00:02Z", full=[H2], bind=[["a.txt", H2]], strong=True, weak=False, fail=False),
        _s("S2", 3, "assistant", "2026-08-01T17:00:03-07:00", full=[H1, H2], abbr=[], bind=[["a.txt", H2]],
           claims=["DONE"]),
        _s("S2", 4, "usage", "2026-08-02T00:00:04Z", total=500, input=400, cached=0, output=100,
           last_input=400, window=1000),
        ev("chain", "2026-08-01T00:00:00Z", src="chain/T", chain="c", seq=1, self=X1, prev=G),
        ev("chain", "2026-08-01T00:00:01Z", src="chain/T", chain="c", seq=2, self=X2, prev=X1),
        ev("chain", "2026-08-01T00:00:02Z", src="chain/T", chain="c", seq=3, self=X3, prev=X2),
        ev("post", "2026-08-02T01:00:00Z", src="board/A", name="p.txt", sha=P1, sidecar="match",
           status="DELIVERED", evidence_line=True, full=[H1], abbr=[], bind=[], claims=["DELIVERED"]),
        ev("post", "2026-08-02T01:00:00Z", src="board/B", name="p.txt", sha=P1, sidecar="match",
           status="DELIVERED", evidence_line=True, full=[H1], abbr=[], bind=[], claims=["DELIVERED"]),
        ev("report", "2026-08-02T02:00:00Z", src="reports/A", name="REPORT-1.md", sha=P2, sidecar="match",
           full=[H2], abbr=[], bind=[], claims=[]),
        ev("register", "2026-08-02T03:00:00Z", src="register/T", id="R1", verdict="PASS", no_receipt=False,
           receipt_nonempty=True, receipt_full=1, receipt_abbr=0),
        ev("fails", "2026-08-02T04:00:00Z", src="fails/T", seq=1, status="CLOSED", evidence_sha=1,
           evidence_items=1, self=F1, prev=G),
        {"kind": "extract_meta", "src": "codex/T", "dropped": {"browser_ctx_texts": 2}},
    ]


GOOD_EXPECTED = {
    "provenance": {"TOOL_SAME_SESSION": 2, "USER_SAME_SESSION": 0, "PRIOR_SESSION": 1, "UNSOURCED": 0},
    "abbr_assistant": {"RESOLVED": 1, "CORRUPT": 0, "UNRESOLVED": 0},
    "binding": {"MATCH_LATEST": 2, "STALE": 0, "NO_EVIDENCE_VALUE": 0, "LABEL_UNSEEN": 0},
    "compaction": {"sessions_with_compaction": 1, "compactions": 1, "carried_mentions": 1,
                   "recalled_without_refetch": 1, "refetched_first": 0, "new_after_compaction": 0},
    "chain_c": {"records": 3, "links_ok": 2, "links_broken": 0, "seq_gaps": 0, "genesis_ok": 1},
    "cross_board": {"distinct_post_names": 1, "boards_per_name": {"2": 1}, "multi_board_identical": 1,
                    "multi_board_divergent": 0},
    "usage_total": {"sessions": 2, "total_tokens": 2500, "fresh_tokens": 1300, "compactions": 1,
                    "sessions_fill_ge_90pct": 1, "distinct_tool_hashes": 2, "backed_positive_claims": 2,
                    "tokens_per_distinct_tool_hash": 1250, "tokens_per_backed_claim": 1250},
    "reasks": {"user_asks": 2, "repeat_within_session": 0, "repeat_from_prior_session": 0},
    "rederivations": {"tool_hash_mentions": 2, "already_seen_same_session": 0, "already_seen_prior_session": 0},
    "positive": {"claims": 2, "backed_strict": 2, "backed_any": 0, "contradicted": 0, "unbacked": 0},
    "posts": {"posts": 2, "with_status": 2, "status_delivered_like": 2, "delivered_with_evidence_hash": 2,
              "delivered_without_evidence": 0},
    "post_sidecar": {"match": 2, "mismatch": 0, "absent": 0, "malformed": 0},
    "report_sidecar": {"match": 1, "mismatch": 0, "absent": 0, "malformed": 0},
    "register_pass": {"hash": 1, "abbr": 0, "reference": 0, "none": 0},
    "fails_closed": {"records": 1, "with_evidence_sha": 1},
    "first_utc": "2026-08-01T00:00:00.000000Z",
    "last_utc": "2026-08-02T04:00:00.000000Z",
    "dropped": {"browser_ctx_texts": 2},
}


def _s3(i, kind, t, **kw):
    return ev(kind, t, src="codex/T", sess="S3", i=i, **kw)


S3 = [_s3(0, "session", "2026-08-03T00:00:00Z")]

# Each defect: (events to add, {metric path: expected value after adding to GOOD}).
DEFECTS = {
    "unsourced_hash": (S3 + [_s3(1, "assistant", "2026-08-03T00:00:01Z", full=[H9], abbr=[], bind=[], claims=[])],
                       {"provenance.UNSOURCED": 1}),
    "corrupt_abbreviation": (S3 + [_s3(1, "assistant", "2026-08-03T00:00:01Z", full=[], abbr=[["1a1a1a1a", "ffff"]],
                                       bind=[], claims=[])],
                             {"abbr_assistant.CORRUPT": 1, "abbr_assistant.RESOLVED": 1}),
    "stale_binding": (S3 + [_s3(1, "assistant", "2026-08-03T00:00:01Z", full=[], abbr=[], bind=[["a.txt", H1]],
                                claims=[])],
                      {"binding.STALE": 1, "binding.MATCH_LATEST": 2}),
    "unbacked_pass": (S3 + [_s3(1, "user", "2026-08-03T00:00:01Z", fp="f000000000000009", full=[], abbr=[], bind=[]),
                            _s3(2, "assistant", "2026-08-03T00:00:02Z", full=[], abbr=[], bind=[], claims=["PASS"])],
                      {"positive.unbacked": 1, "positive.claims": 3}),
    "contradicted_delivered": (S3 + [_s3(1, "tool", "2026-08-03T00:00:01Z", full=[], bind=[], strong=False, weak=False,
                                         fail=True),
                                     _s3(2, "assistant", "2026-08-03T00:00:02Z", full=[], abbr=[], bind=[],
                                         claims=["DELIVERED"])],
                               {"positive.contradicted": 1, "positive.backed_strict": 2}),
    "reask_prior_session": (S3 + [_s3(1, "user", "2026-08-03T00:00:01Z", fp="f000000000000001", full=[], abbr=[],
                                      bind=[])],
                            {"reasks.repeat_from_prior_session": 1, "reasks.user_asks": 3}),
    "reask_within_session": (S3 + [_s3(1, "user", "2026-08-03T00:00:01Z", fp="f000000000000009", full=[], abbr=[],
                                       bind=[]),
                                   _s3(2, "user", "2026-08-03T00:00:02Z", fp="f000000000000009", full=[], abbr=[],
                                       bind=[])],
                             {"reasks.repeat_within_session": 1, "reasks.user_asks": 4}),
    "rederived_hash": (S3 + [_s3(1, "tool", "2026-08-03T00:00:01Z", full=[H2], bind=[], strong=True, weak=False,
                                 fail=False)],
                       {"rederivations.already_seen_prior_session": 1, "rederivations.tool_hash_mentions": 3}),
    "lost_after_compaction_refetch": (
        [_s("S1", 8, "compaction", "2026-08-01T00:00:08Z"),
         _s("S1", 9, "tool", "2026-08-01T00:00:09Z", full=[H1], bind=[], strong=True, weak=False, fail=False),
         _s("S1", 10, "assistant", "2026-08-01T00:00:10Z", full=[H1], abbr=[], bind=[], claims=[])],
        {"compaction.refetched_first": 1, "compaction.carried_mentions": 2, "compaction.compactions": 2}),
    "broken_chain_link": ([ev("chain", "2026-08-01T00:00:03Z", src="chain/T", chain="c", seq=5, self="c5" * 32,
                              prev=X1)],
                          {"chain_c.links_broken": 1, "chain_c.seq_gaps": 1, "chain_c.records": 4}),
    "divergent_board_copy": ([ev("post", "2026-08-02T01:00:00Z", src="board/C", name="p.txt", sha=P2,
                                 sidecar="mismatch", status="DELIVERED", evidence_line=False, full=[], abbr=[],
                                 bind=[], claims=["DELIVERED"])],
                             {"cross_board.multi_board_divergent": 1, "cross_board.multi_board_identical": 0,
                              "posts.delivered_without_evidence": 1, "post_sidecar.mismatch": 1}),
    "report_sidecar_mismatch": ([ev("report", "2026-08-02T02:30:00Z", src="reports/A", name="REPORT-2.md", sha=P1,
                                    sidecar="mismatch", full=[], abbr=[], bind=[], claims=[])],
                                {"report_sidecar.mismatch": 1}),
    "register_pass_no_receipt": ([ev("register", "2026-08-02T03:30:00Z", src="register/T", id="R2", verdict="PASS",
                                     no_receipt=True, receipt_nonempty=False, receipt_full=0, receipt_abbr=0)],
                                 {"register_pass.none": 1}),
    "fails_closed_without_evidence": ([ev("fails", "2026-08-02T04:30:00Z", src="fails/T", seq=2, status="CLOSED",
                                          evidence_sha=0, evidence_items=0, self="f2" * 32, prev=F1)],
                                      {"fails_closed.records": 2, "fails_closed.with_evidence_sha": 1}),
}
