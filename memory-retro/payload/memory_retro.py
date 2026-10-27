"""Grok Bot - ROUND-SEAT

memory-retro v0: deterministic retrospective scorer for AI memory continuity,
context usage effectiveness and operational awareness.

run(request) is a pure function over a typed request holding privacy-minimal
extracted events (no message text). It reads no files, opens no network and
starts no processes. Every metric is integer counts plus exact ratio strings.
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone

HEADER = "Grok Bot - ROUND-SEAT"
REQ = "agape.memretro.request.v0"
RES = "agape.memretro.result.v0"
POSITIVE = {"PASS", "MATCH", "DONE", "DELIVERED", "VERIFIED"}
NEGATIVE = {"FAIL", "MISMATCH", "FAILED"}
PROGRESS = {"LAUNCHED", "OUTPUT_GROWING"}
ABSTAIN = {"HOLD", "NOT_RUN", "UNKNOWN"}
DOCS = ("post", "report")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
TS = re.compile(r"(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d)(?::(\d\d)(?:\.(\d+))?)?\s*(Z|[+-]\d\d:?\d\d)?\Z")
GENESIS = "0" * 64


def norm_t(value):
    """Normalize an ISO-8601 time to UTC 'YYYY-MM-DDTHH:MM:SS.ffffffZ'; '' if absent/invalid."""
    if not isinstance(value, str):
        return ""
    m = TS.match(value.strip())
    if not m:
        return ""
    y, mo, d, h, mi, s, frac, tz = m.groups()
    us = int((frac or "0")[:6].ljust(6, "0"))
    dt = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0), us)
    if tz and tz != "Z":
        sign = 1 if tz[0] == "+" else -1
        tz = tz[1:].replace(":", "")
        dt -= sign * timedelta(hours=int(tz[:2]), minutes=int(tz[2:]))
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def ratio(num, den):
    return {"num": num, "den": den, "rate": "%.4f" % (num / den) if den else "n/a"}


def _key(ev):
    return (ev["_t"], ev.get("src", ""), str(ev.get("sess", "")), ev.get("i", 0), ev["_n"])


def _prepare(events):
    out = []
    for n, ev in enumerate(events):
        if type(ev) is not dict or not isinstance(ev.get("kind"), str):
            raise ValueError("event %d shape" % n)
        e = dict(ev)
        e["_t"] = norm_t(ev.get("t"))
        e["_n"] = n
        out.append(e)
    out.sort(key=_key)
    return out


def _sessions(evs):
    sess = {}
    for e in evs:
        if e.get("sess") is not None and e["kind"] not in ("extract_meta",):
            sess.setdefault((e.get("src", ""), str(e["sess"])), []).append(e)
    for v in sess.values():
        v.sort(key=lambda e: (e.get("i", 0), e["_n"]))
    return sess


def _full(e):
    return [h for h in e.get("full") or [] if isinstance(h, str) and HEX64.match(h)]


# ---------------- (a) memory continuity ----------------

def hash_provenance(evs, sessions):
    """Each (session, hash) first mentioned by the assistant: where did it come from?"""
    first_seen = {}  # hash -> earliest _t from any event outside a given session (computed lazily)
    seen_by = {}
    for e in evs:
        for h in _full(e):
            seen_by.setdefault(h, []).append((e["_t"], e.get("src", ""), str(e.get("sess", "")), e["kind"]))
    counts = {"TOOL_SAME_SESSION": 0, "USER_SAME_SESSION": 0, "PRIOR_SESSION": 0, "UNSOURCED": 0}
    for (src, sid), items in sorted(sessions.items()):
        tool_seen, user_seen, done = set(), set(), set()
        for e in items:
            if e["kind"] == "tool":
                tool_seen.update(_full(e))
            elif e["kind"] == "user":
                user_seen.update(_full(e))
            elif e["kind"] == "assistant":
                for h in _full(e):
                    if h in done:
                        continue
                    done.add(h)
                    if h in tool_seen:
                        counts["TOOL_SAME_SESSION"] += 1
                    elif h in user_seen:
                        counts["USER_SAME_SESSION"] += 1
                    elif any(t and e["_t"] and t < e["_t"] and (s2 != sid or k in DOCS)
                             for t, _s, s2, k in seen_by.get(h, ())):
                        counts["PRIOR_SESSION"] += 1
                    else:
                        counts["UNSOURCED"] += 1
    total = sum(counts.values())
    return {"counts": counts, "total": total,
            "sourced": ratio(total - counts["UNSOURCED"], total)}


def abbreviation_fidelity(evs):
    """Abbreviated hashes (prefix...suffix) checked against every full hash in the corpus."""
    known = sorted({h for e in evs for h in _full(e)})
    by_prefix = {}
    for h in known:
        by_prefix.setdefault(h[:6], []).append(h)
    out = {}
    for scope in ("assistant", "doc"):
        out[scope] = {"RESOLVED": 0, "CORRUPT": 0, "UNRESOLVED": 0}
    for e in evs:
        scope = "assistant" if e["kind"] == "assistant" else "doc" if e["kind"] in DOCS else None
        if scope is None:
            continue
        for pair in e.get("abbr") or []:
            if not (isinstance(pair, list) and len(pair) == 2):
                continue
            p, s = str(pair[0]).lower(), str(pair[1]).lower()
            if len(p) < 6:
                continue
            cands = [h for h in by_prefix.get(p[:6], ()) if h.startswith(p)]
            if any(h.endswith(s) for h in cands):
                out[scope]["RESOLVED"] += 1
            elif cands and s and len(p) >= 8:
                out[scope]["CORRUPT"] += 1
            else:
                out[scope]["UNRESOLVED"] += 1
    for scope in out:
        c = out[scope]
        out[scope] = {"counts": c, "corrupt_of_checkable": ratio(c["CORRUPT"], c["CORRUPT"] + c["RESOLVED"])}
    return out


def binding_consistency(evs, after_compaction=None):
    """Assistant label->sha256 statements vs the latest evidence value (tool output on the
    same source, or any board post / desk report) known at that moment."""
    latest, history = {}, {}
    counts = {"MATCH_LATEST": 0, "STALE": 0, "NO_EVIDENCE_VALUE": 0, "LABEL_UNSEEN": 0}
    post = {"MATCH_LATEST": 0, "STALE": 0, "NO_EVIDENCE_VALUE": 0, "LABEL_UNSEEN": 0}
    for e in evs:
        k = e["kind"]
        binds = [b for b in e.get("bind") or [] if isinstance(b, list) and len(b) == 2
                 and isinstance(b[1], str) and HEX64.match(b[1])]
        if k in ("tool",) + DOCS:
            scope = e.get("src", "") if k == "tool" else "*"
            for lab, v in binds:
                latest[(scope, lab)] = (e["_t"], v)
                history.setdefault((scope, lab), set()).add(v)
        elif k == "assistant":
            for lab, v in binds:
                cand = [latest[x] for x in ((e.get("src", ""), lab), ("*", lab)) if x in latest]
                hist = history.get((e.get("src", ""), lab), set()) | history.get(("*", lab), set())
                if not cand:
                    c = "LABEL_UNSEEN"
                else:
                    cur = max(cand)[1]
                    c = "MATCH_LATEST" if v == cur else "STALE" if v in hist else "NO_EVIDENCE_VALUE"
                counts[c] += 1
                if after_compaction is not None and e.get("_postc"):
                    post[c] += 1
    res = {"counts": counts, "stale_of_checkable": ratio(counts["STALE"], counts["STALE"] + counts["MATCH_LATEST"])}
    if after_compaction is not None:
        res["after_compaction"] = {"counts": post,
                                   "stale_of_checkable": ratio(post["STALE"], post["STALE"] + post["MATCH_LATEST"])}
    return res


def compaction_recall(sessions):
    """After a context compaction, hashes the assistant states that were already seen in the
    session before the compaction: recalled directly vs re-fetched by a tool first."""
    out = {"sessions_with_compaction": 0, "compactions": 0, "carried_mentions": 0,
           "recalled_without_refetch": 0, "refetched_first": 0, "new_after_compaction": 0}
    for _key_, items in sorted(sessions.items()):
        pre, compacted, post_tool = set(), False, set()
        n_c = sum(1 for e in items if e["kind"] == "compaction")
        if n_c:
            out["sessions_with_compaction"] += 1
            out["compactions"] += n_c
        for e in items:
            if e["kind"] == "compaction":
                compacted = True
                post_tool = set()
                continue
            if compacted:
                e["_postc"] = True
            if not compacted:
                pre.update(_full(e))
            elif e["kind"] == "tool":
                post_tool.update(_full(e))
            elif e["kind"] == "assistant":
                for h in _full(e):
                    if h in pre:
                        out["carried_mentions"] += 1
                        if h in post_tool:
                            out["refetched_first"] += 1
                        else:
                            out["recalled_without_refetch"] += 1
                    else:
                        out["new_after_compaction"] += 1
    return out


def chain_integrity(evs):
    """Hash-linked logs: seq continuity and prev-link == previous record's self value."""
    chains = {}
    for e in evs:
        if e["kind"] in ("chain", "fails"):
            name = e.get("chain") or "fails"
            chains.setdefault("%s|%s" % (e.get("src", ""), name), []).append(e)
    out = {}
    for name in sorted(chains):
        recs = chains[name]
        try:
            recs = sorted(recs, key=lambda e: (int(e.get("seq")), e["_n"]))
        except (TypeError, ValueError):
            out[name] = {"records": len(recs), "error": "non-integer seq"}
            continue
        r = {"records": len(recs), "links_ok": 0, "links_broken": 0, "seq_gaps": 0, "seq_dups": 0,
             "genesis_ok": 0, "excluded_privacy": sum(1 for e in recs if e.get("excluded")),
             "sidecar_match": sum(1 for e in recs if e.get("sidecar") == "match"),
             "sidecar_mismatch": sum(1 for e in recs if e.get("sidecar") == "mismatch")}
        first = recs[0]
        if first.get("prev") in (None, "", GENESIS, "GENESIS"):
            r["genesis_ok"] = 1
        for a, b in zip(recs, recs[1:]):
            sa, sb = int(a["seq"]), int(b["seq"])
            if sb == sa:
                r["seq_dups"] += 1
            elif sb != sa + 1:
                r["seq_gaps"] += 1
            if b.get("prev") is not None and b.get("prev") == a.get("self"):
                r["links_ok"] += 1
            else:
                r["links_broken"] += 1
        r["first_seq"], r["last_seq"] = int(recs[0]["seq"]), int(recs[-1]["seq"])
        r["link_integrity"] = ratio(r["links_ok"], r["links_ok"] + r["links_broken"])
        out[name] = r
    return out


def cross_board_identity(evs):
    names = {}
    for e in evs:
        if e["kind"] == "post":
            names.setdefault(e.get("name"), {})[e.get("src", "")] = e.get("sha")
    spread = {}
    identical = divergent = 0
    for n, by in names.items():
        spread[str(len(by))] = spread.get(str(len(by)), 0) + 1
        if len(by) > 1:
            if len(set(by.values())) == 1:
                identical += 1
            else:
                divergent += 1
    return {"distinct_post_names": len(names), "boards_per_name": dict(sorted(spread.items())),
            "multi_board_identical": identical, "multi_board_divergent": divergent}


# ---------------- (b) context usage effectiveness ----------------

def context_usage(evs, sessions, claims_backed):
    per_src, per_month = {}, {}
    rederive_cross = rederive_within = 0
    reask_within = reask_cross = user_asks = 0
    tool_hash_events = 0
    seen_tool_src, seen_fp_src = {}, {}
    for (src, sid), items in sorted(sessions.items(), key=lambda kv: (kv[1][0]["_t"], kv[0])):
        usage = [e for e in items if e["kind"] == "usage"]
        if not usage and not any(e["kind"] in ("user", "assistant", "tool") for e in items):
            continue
        tot = max([int(e.get("total", 0)) for e in usage] or [0])
        last = max(usage, key=lambda e: (int(e.get("total", 0)), e.get("i", 0))) if usage else {}
        fresh = int(last.get("input", 0)) - int(last.get("cached", 0)) + int(last.get("output", 0)) if usage else 0
        fills = [int(e.get("last_input", 0)) / int(e["window"]) for e in usage if int(e.get("window", 0) or 0) > 0]
        start = next((e["_t"] for e in items if e["_t"]), "")
        month = start[:7] or "unknown"
        comp = sum(1 for e in items if e["kind"] == "compaction")
        tool_h, fps = set(), set()
        prior_tool = seen_tool_src.setdefault(src, set())
        prior_fp = seen_fp_src.setdefault(src, set())
        for e in items:
            if e["kind"] == "tool":
                for h in _full(e):
                    tool_hash_events += 1
                    if h in tool_h:
                        rederive_within += 1
                    elif h in prior_tool:
                        rederive_cross += 1
                    tool_h.add(h)
            elif e["kind"] == "user" and e.get("fp"):
                user_asks += 1
                if e["fp"] in fps:
                    reask_within += 1
                elif e["fp"] in prior_fp:
                    reask_cross += 1
                fps.add(e["fp"])
        prior_tool |= tool_h
        prior_fp |= fps
        b = claims_backed.get((src, sid), 0)
        for bucket, key in ((per_src, src), (per_month, month)):
            a = bucket.setdefault(key, {"sessions": 0, "total_tokens": 0, "fresh_tokens": 0, "compactions": 0,
                                        "sessions_fill_ge_90pct": 0, "distinct_tool_hashes": 0,
                                        "backed_positive_claims": 0})
            a["sessions"] += 1
            a["total_tokens"] += tot
            a["fresh_tokens"] += fresh
            a["compactions"] += comp
            a["sessions_fill_ge_90pct"] += 1 if fills and max(fills) >= 0.9 else 0
            a["distinct_tool_hashes"] += len(tool_h)
            a["backed_positive_claims"] += b
    for bucket in (per_src, per_month):
        for a in bucket.values():
            a["tokens_per_distinct_tool_hash"] = a["total_tokens"] // a["distinct_tool_hashes"] if a["distinct_tool_hashes"] else None
            a["tokens_per_backed_claim"] = a["total_tokens"] // a["backed_positive_claims"] if a["backed_positive_claims"] else None
    total = {k: sum(a[k] for a in per_src.values()) for k in
             ("sessions", "total_tokens", "fresh_tokens", "compactions", "sessions_fill_ge_90pct",
              "distinct_tool_hashes", "backed_positive_claims")}
    total["tokens_per_distinct_tool_hash"] = total["total_tokens"] // total["distinct_tool_hashes"] if total["distinct_tool_hashes"] else None
    total["tokens_per_backed_claim"] = total["total_tokens"] // total["backed_positive_claims"] if total["backed_positive_claims"] else None
    return {"total": total, "per_source": dict(sorted(per_src.items())), "per_month": dict(sorted(per_month.items())),
            "reasks": {"user_asks": user_asks, "repeat_within_session": reask_within,
                       "repeat_from_prior_session": reask_cross,
                       "rate": ratio(reask_within + reask_cross, user_asks)},
            "rederivations": {"tool_hash_mentions": tool_hash_events, "already_seen_same_session": rederive_within,
                              "already_seen_prior_session": rederive_cross,
                              "prior_session_rate": ratio(rederive_cross, tool_hash_events)}}


# ---------------- (c) operational awareness ----------------

def claim_backing(sessions):
    """Assistant status claims vs tool evidence earlier in the same turn (since last user ask)."""
    c = {cls: {"claims": 0, "backed_strict": 0, "backed_any": 0, "contradicted": 0, "unbacked": 0}
         for cls in ("positive", "negative", "progress")}
    abstain = 0
    backed_per_session = {}
    for key, items in sorted(sessions.items()):
        turn = []
        for e in items:
            k = e["kind"]
            if k == "user":
                turn = []
            elif k == "tool":
                turn.append(e)
            elif k == "assistant":
                cl = set(e.get("claims") or [])
                abstain += 1 if cl & ABSTAIN else 0
                for cls, words in (("positive", POSITIVE), ("negative", NEGATIVE), ("progress", PROGRESS)):
                    if not cl & words:
                        continue
                    r = c[cls]
                    r["claims"] += 1
                    if cls == "positive":
                        strict = any(t.get("strong") and not t.get("fail") for t in turn)
                        contra = bool(turn) and turn[-1].get("fail") and not turn[-1].get("strong")
                    elif cls == "negative":
                        strict = any(t.get("fail") for t in turn)
                        contra = False
                    else:
                        strict = bool(turn)
                        contra = False
                    if contra:
                        r["contradicted"] += 1
                    elif strict:
                        r["backed_strict"] += 1
                        if cls == "positive":
                            backed_per_session[key] = backed_per_session.get(key, 0) + 1
                    elif turn:
                        r["backed_any"] += 1
                    else:
                        r["unbacked"] += 1
    for r in c.values():
        r["strict_rate"] = ratio(r["backed_strict"], r["claims"])
        r["unbacked_rate"] = ratio(r["unbacked"], r["claims"])
    return {"by_class": c, "abstain_messages": abstain}, backed_per_session


def doc_receipts(evs):
    posts = {"posts": 0, "with_status": 0, "status_delivered_like": 0, "delivered_with_evidence_hash": 0,
             "delivered_without_evidence": 0, "sidecar": {"match": 0, "mismatch": 0, "absent": 0, "malformed": 0}}
    reps = {"reports": 0, "with_full_hash": 0, "sidecar": {"match": 0, "mismatch": 0, "absent": 0, "malformed": 0}}
    for e in evs:
        if e["kind"] == "post":
            posts["posts"] += 1
            posts["sidecar"][e.get("sidecar", "absent")] = posts["sidecar"].get(e.get("sidecar", "absent"), 0) + 1
            st = (e.get("status") or "").upper()
            if st:
                posts["with_status"] += 1
            if st in POSITIVE:
                posts["status_delivered_like"] += 1
                if e.get("evidence_line") and (_full(e) or e.get("abbr")):
                    posts["delivered_with_evidence_hash"] += 1
                else:
                    posts["delivered_without_evidence"] += 1
        elif e["kind"] == "report":
            reps["reports"] += 1
            reps["sidecar"][e.get("sidecar", "absent")] = reps["sidecar"].get(e.get("sidecar", "absent"), 0) + 1
            reps["with_full_hash"] += 1 if _full(e) else 0
    return posts, reps


def register_and_fails(evs):
    reg = {}
    for e in evs:
        if e["kind"] == "register":
            v = e.get("verdict") or "BLANK"
            if v not in ("PASS", "DEGRADED", "HOLD", "UNKNOWN"):
                v = "OTHER"
            tier = "hash" if e.get("receipt_full") else "abbr" if e.get("receipt_abbr") else \
                "none" if e.get("no_receipt") else "reference"
            reg.setdefault(v, {"hash": 0, "abbr": 0, "reference": 0, "none": 0})[tier] += 1
    pv = reg.get("PASS", {"hash": 0, "abbr": 0, "reference": 0, "none": 0})
    fails = {}
    for e in evs:
        if e["kind"] == "fails":
            s = e.get("status") or "BLANK"
            a = fails.setdefault(s, {"records": 0, "with_evidence_sha": 0})
            a["records"] += 1
            a["with_evidence_sha"] += 1 if e.get("evidence_sha") else 0
    return {"register": {"by_verdict": dict(sorted(reg.items())),
                         "pass_with_hash_receipt": ratio(pv["hash"], sum(pv.values())),
                         "pass_with_no_receipt": pv["none"]},
            "fails_ledger": dict(sorted(fails.items()))}


def coverage(evs):
    cov = {}
    for e in evs:
        if e["kind"] == "extract_meta":
            continue
        a = cov.setdefault(e.get("src", ""), {"events": 0, "kinds": {}, "first_utc": "", "last_utc": "",
                                               "sessions": set()})
        a["events"] += 1
        a["kinds"][e["kind"]] = a["kinds"].get(e["kind"], 0) + 1
        if e["_t"]:
            a["first_utc"] = min(a["first_utc"] or e["_t"], e["_t"])
            a["last_utc"] = max(a["last_utc"], e["_t"])
        if e["kind"] == "session":
            a["sessions"].add(str(e.get("sess")))
    for a in cov.values():
        a["sessions"] = len(a["sessions"])
        a["kinds"] = dict(sorted(a["kinds"].items()))
    dropped = {}
    for e in evs:
        if e["kind"] == "extract_meta":
            for k, v in (e.get("dropped") or {}).items():
                dropped[k] = dropped.get(k, 0) + int(v)
    return dict(sorted(cov.items())), dict(sorted(dropped.items()))


def run(request):
    """Score one agape.memretro.request.v0 and return agape.memretro.result.v0."""
    if type(request) is not dict or not {"schema", "events"} <= set(request) or \
            not set(request) <= {"schema", "events", "not_run", "label"}:
        raise ValueError("request fields")
    if request["schema"] != REQ:
        raise ValueError("request schema")
    if type(request["events"]) is not list:
        raise ValueError("events list")
    evs = _prepare(request["events"])
    sessions = _sessions(evs)
    comp = compaction_recall(sessions)  # marks post-compaction events
    backing, backed_per_session = claim_backing(sessions)
    posts, reps = doc_receipts(evs)
    cov, dropped = coverage(evs)
    times = sorted(e["_t"] for e in evs if e["_t"] and e["kind"] != "extract_meta")
    return {
        "header": HEADER, "schema": RES, "status": "delivered",
        "label": str(request.get("label", "")),
        "coverage": {"events": len(evs), "first_utc": times[0] if times else "", "last_utc": times[-1] if times else "",
                     "by_source": cov, "privacy_dropped": dropped,
                     "not_run": sorted(request.get("not_run") or [])},
        "memory_continuity": {
            "hash_provenance": hash_provenance(evs, sessions),
            "abbreviation_fidelity": abbreviation_fidelity(evs),
            "binding_consistency": binding_consistency(evs, after_compaction=True),
            "compaction_recall": comp,
            "chain_integrity": chain_integrity(evs),
            "cross_board_identity": cross_board_identity(evs),
        },
        "context_usage": context_usage(evs, sessions, backed_per_session),
        "operational_awareness": {
            "assistant_claims": backing,
            "board_posts": posts,
            "desk_reports": reps,
            **register_and_fails(evs),
        },
    }


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_):
    raise ValueError("non-finite JSON number")


def main():
    try:
        request = json.loads(sys.stdin.buffer.read().decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        result = run(request)
    except (ValueError, UnicodeError, RecursionError) as exc:
        print(json.dumps({"header": HEADER, "status": "failed", "error": str(exc)}, ensure_ascii=True, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
