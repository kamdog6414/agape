#!/usr/bin/env python3
"""agape-eta learn: automatic, stdlib-only, no LLM. Runs inside the 5-minute eta_run pass.
Ledger: calibration.jsonl, append-only, hash-chained with the FullCircle FAILS-LEDGER convention
(hash = sha256(canonical JSON of all fields except 'hash', sorted keys, no spaces, UTF-8); genesis prev_hash = 64 zeros).
Every forecast/calibration is a falsifiable CLAIM with a falsifier; verdict codes follow the fails falsifier
contract: 0 = HOLDS/PASS, 1 = FAIL (falsified), 2 = UNKNOWN.
Record types: SCORE (a forecast checked against an observed finish), OBS (throughput of a finished job),
CAL (per-kind calibration learned from SCOREs; itself a claim falsified by the next SCORE)."""
import os, json, time, hashlib, statistics
from datetime import datetime
HERE = os.path.dirname(os.path.abspath(__file__))
CAL = os.path.join(HERE, "calibration.jsonl")
GEN = "0" * 64
TARGET = 0.80

def canon(o): return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def rec_hash(r): return hashlib.sha256(canon({k: v for k, v in r.items() if k != "hash"}).encode("utf-8")).hexdigest()
def iso(t=None): return datetime.fromtimestamp(time.time() if t is None else t).astimezone().isoformat(timespec="seconds")

def records(path=CAL):
    if not os.path.exists(path): return []
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]

def append(fields, path=CAL):
    rs = records(path); prev = rs[-1] if rs else None
    r = dict(fields)
    if "config" not in r:
        try:
            import qgate; r["config"] = qgate.config(HERE)
        except Exception as e: r["config"] = {"manifest_hash": "UNKNOWN", "error": e.__class__.__name__}
    r.update(v=1, seq=(prev["seq"] + 1) if prev else 1, prev_hash=prev["hash"] if prev else GEN)
    r.setdefault("ts", iso()); r["hash"] = rec_hash(r)
    with open(path, "a", encoding="utf-8") as f: f.write(canon(r) + "\n")
    return r

def verify(path=CAL):
    prev, n = GEN, 0
    for i, r in enumerate(records(path), 1):
        if r.get("prev_hash") != prev or rec_hash(r) != r.get("hash") or r.get("seq") != i: return "BREAK at seq %d" % i
        prev = r["hash"]; n += 1
    return "OK %d records head %s" % (n, prev[:16])

def q(xs, p):
    xs = sorted(xs)
    if len(xs) == 1: return xs[0]
    k = (len(xs) - 1) * p; i = int(k); j = min(i + 1, len(xs) - 1)
    return xs[i] + (xs[j] - xs[i]) * (k - i)

# ---------- scoring ----------
def score(fc, fin, kind, node, source="auto", fin_note=None, path=CAL):
    """fc: forecast dict with as_of (or made_at), eta_p10/50/90 (adjusted, as claimed) and optional raw_p10/50/90."""
    if any(r.get("type") == "SCORE" and r.get("forecast_hash") == fc.get("hash") and fc.get("hash") for r in records(path)): return None
    p10, p50, p90 = fc.get("eta_p10"), fc.get("eta_p50"), fc.get("eta_p90")
    base = fc.get("made_at_claim") or fc.get("as_of")
    raw50 = fc.get("raw_p50", p50); raw10 = fc.get("raw_p10", p10); raw90 = fc.get("raw_p90", p90)
    h = (raw50 - base) if (raw50 is not None and base is not None) else None
    inside = None if p10 is None or p90 is None else (p10 <= fin <= p90)
    rec = {"type": "SCORE", "node": node, "job": fc.get("job"), "kind": kind, "source": source,
           "forecast_hash": fc.get("hash"), "as_of": base, "finished": fin, "finished_iso": iso(fin),
           "claim": "job %s finishes inside P10..P90 [%s .. %s], P50 %s" % (fc.get("job"), iso(p10) if p10 else "none", iso(p90) if p90 else "none", iso(p50) if p50 else "none"),
           "falsifier": "observed finish outside [P10,P90] => FAIL(1); no range => UNKNOWN(2)",
           "err_min_p50": None if p50 is None else round((fin - p50) / 60, 2),
           "raw_err_min_p50": None if raw50 is None else round((fin - raw50) / 60, 2),
           "rel_err": None if not h or h <= 0 else round((fin - raw50) / h, 4),
           "rel_lo": None if not h or h <= 0 or raw10 is None else round((raw10 - raw50) / h, 4),
           "rel_hi": None if not h or h <= 0 or raw90 is None else round((raw90 - raw50) / h, 4),
           "inside_range": inside, "verdict": 2 if inside is None else (0 if inside else 1)}
    if fin_note: rec["finish_note"] = fin_note
    return append(rec, path)

def observe(node, kind, job, start, fin, total, unit, source, note=None, path=CAL):
    if any(r.get("type") == "OBS" and r.get("job") == job and r.get("finished") == fin for r in records(path)): return None
    rate = (total / (fin - start)) if (start is not None and fin and total and fin > start) else None
    rec = {"type": "OBS", "node": node, "kind": kind, "job": job, "start": start, "finished": fin, "total": total, "unit": unit,
           "rate_per_s": None if rate is None else round(rate, 3), "source": source,
           "claim": "throughput %s %s/s for %s on %s" % ("UNKNOWN" if rate is None else "%.3f" % rate, unit, kind, node),
           "falsifier": "recompute total/(finished-start) from cited evidence; mismatch >1% => FAIL(1)"}
    if note: rec["note"] = note
    return append(rec, path)

# ---------- learning ----------
def learn(kind, path=CAL):
    S = [r for r in records(path) if r.get("type") == "SCORE" and r.get("kind") == kind]
    if not S: return None
    errs = [r["raw_err_min_p50"] for r in S if r.get("raw_err_min_p50") is not None]
    rel = [r["rel_err"] for r in S if r.get("rel_err") is not None]
    ins = [r["inside_range"] for r in S if r.get("inside_range") is not None]
    c = {"kind": kind, "n": len(S), "n_rel": len(rel),
         "median_err_min": round(statistics.median(errs), 2) if errs else None,
         "spread_err_min": round(q(errs, .9) - q(errs, .1), 2) if len(errs) >= 2 else None,
         "coverage": round(sum(ins) / len(ins), 3) if ins else None, "n_cov": len(ins)}
    if rel:
        c["shift_rel"] = round(statistics.median(rel), 4)          # move P50 by this fraction of the horizon
        if len(rel) >= 3:                                         # empirical 10/90% quantiles of relative residuals
            c["lo_rel"] = round(min(q(rel, .10) - c["shift_rel"], -0.05), 4)
            c["hi_rel"] = round(max(q(rel, .90) - c["shift_rel"], 0.05), 4)
    return c

def calibrate_all(node, path=CAL):
    kinds = sorted({r["kind"] for r in records(path) if r.get("type") == "SCORE" and r.get("kind")})
    last = {}
    for r in records(path):
        if r.get("type") == "CAL": last[r["kind"]] = r
    out = {}
    for k in kinds:
        c = learn(k, path); out[k] = c
        if c is None: continue
        old = last.get(k); key = lambda x: {kk: x.get(kk) for kk in c}
        if not old or key(old) != c:
            rec = dict(c); rec.update(type="CAL", node=node,
                claim="for kind %s, P50 shifted by %s of horizon and P10..P90 from residual quantiles covers >= %.0f%% of finishes" % (k, c.get("shift_rel"), TARGET * 100),
                falsifier="rolling coverage of adjusted ranges over the next >=5 SCOREs of this kind < %.0f%% => FAIL(1); n<5 => UNKNOWN(2)" % (TARGET * 100 - 15))
            append(rec, path)
    return out

def adjust(fc, kind, now, path=CAL):
    """Return (fc', label). Learned shift/widen applied to a raw forecast; raw values kept."""
    if not fc or fc.get("eta_p50") is None: return fc, cal_label(kind, path)
    c = learn(kind, path); f = dict(fc)
    f.update(raw_p10=fc["eta_p10"], raw_p50=fc["eta_p50"], raw_p90=fc["eta_p90"])
    if c and c.get("shift_rel") is not None:
        h = max(fc["eta_p50"] - now, 1.0); s = max(c["shift_rel"], -0.9)
        p50 = now + h * (1 + s)
        if "lo_rel" in c:
            p10 = now + h * max(1 + s + c["lo_rel"], 0.02); p90 = now + h * (1 + s + c["hi_rel"])
        else:   # too few scores for quantiles: keep raw width, centred on shifted P50
            p10 = p50 - (fc["eta_p50"] - fc["eta_p10"]); p90 = p50 + (fc["eta_p90"] - fc["eta_p50"])
        f.update(eta_p10=max(min(p10, p50), now), eta_p50=p50, eta_p90=max(p90, p50))
        f.setdefault("notes", []); f["notes"] = list(f["notes"]) + ["CAL %s: shift %+.0f%% of horizon (n=%d)" % (kind, 100 * s, c["n"])]
    return f, cal_label(kind, path)

def cal_label(kind, path=CAL):
    c = learn(kind, path)
    if not c: return "cal: none"
    s = "cal: %+.0fm n=%d" % (c["median_err_min"], c["n"]) if c.get("median_err_min") is not None else "cal: ? n=%d" % c["n"]
    if c.get("coverage") is not None: s += " cov %d%%" % round(100 * c["coverage"])
    return s

def prior_rate(node, kind, path=CAL):
    rs = [r["rate_per_s"] for r in records(path) if r.get("type") == "OBS" and r.get("kind") == kind and r.get("rate_per_s")
          and r.get("node") in (node, None)]
    if not rs: rs = [r["rate_per_s"] for r in records(path) if r.get("type") == "OBS" and r.get("kind") == kind and r.get("rate_per_s")]
    return (statistics.median(rs), len(rs)) if rs else (None, 0)

def report(path=CAL):
    print("calibration.jsonl", verify(path))
    for k in sorted({r["kind"] for r in records(path) if r.get("type") in ("SCORE", "OBS")}):
        c = learn(k, path); pr = [r for r in records(path) if r.get("type") == "OBS" and r.get("kind") == k]
        print("kind %-14s %s | priors %s" % (k, json.dumps(c, sort_keys=True) if c else "no scores",
              ", ".join("%s %s/s" % (r["node"], r["rate_per_s"]) for r in pr) or "none"))

if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["verify"]: print(verify())
    else: report()
