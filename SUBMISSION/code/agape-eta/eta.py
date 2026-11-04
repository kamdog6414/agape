#!/usr/bin/env python3
"""agape-eta: realistic ETA from real-work units. Pure stdlib, B&W text.
eta.py watch <log> --unit articles --total N [--regex R] [--proxy-regex R] [--job J] [--window-min 15] [--at "YYYY-MM-DD HH:MM"] [--no-record]
eta.py score --job J --finished "YYYY-MM-DD HH:MM:SS"
eta.py report
Samples: JSONL lines {"ts": epoch|"YYYY-MM-DD HH:MM:SS", "done": n, "total": n?, "proxy_pct": x?} or a text log + --regex
(named groups ts, done, optional total, optional proxy_pct)."""
import sys, os, re, json, time, hashlib, argparse, statistics
from datetime import datetime
HOME = os.path.dirname(os.path.abspath(__file__))
FC = os.path.join(HOME, "forecasts.jsonl")
SC = os.path.join(HOME, "scores.jsonl")
ZERO = "0" * 64
DEF_RE = r"^(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d).*?\((?P<proxy_pct>[\d.]+)%\) articles_hashed=(?P<done>\d+)"

def pts(s):
    if isinstance(s, (int, float)): return float(s)
    s = str(s).strip()
    if s.endswith("Z") or "T" in s[:19]:
        import calendar
        d = datetime.strptime(s[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
        return float(calendar.timegm(d.timetuple())) if s.endswith("Z") else time.mktime(d.timetuple())
    return time.mktime(datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").timetuple())
def fts(t): return time.strftime("%Y-%m-%d %H:%M %Z", time.localtime(t))

TAIL = 262144
def tail_lines(path, n=TAIL):
    with open(path, "rb") as f:
        f.seek(0, 2); sz = f.tell(); f.seek(max(0, sz - n))
        data = f.read().decode("utf-8", "replace").splitlines()
    return data[1:] if sz > n else data
def load(path, rx):
    out = []
    if True:
        for line in tail_lines(path):
            line = line.strip()
            if not line: continue
            if line.startswith("{"):
                try:
                    d = json.loads(line); out.append({"ts": pts(d["ts"]), "done": float(d["done"]),
                        "total": d.get("total"), "proxy_pct": d.get("proxy_pct")}); continue
                except Exception: pass
            m = re.search(rx, line)
            if m:
                g = m.groupdict()
                out.append({"ts": pts(g["ts"]), "done": float(g["done"]), "total": g.get("total"),
                            "proxy_pct": float(g["proxy_pct"]) if g.get("proxy_pct") else None})
    return sorted(out, key=lambda s: s["ts"])

def pct(xs, q):
    xs = sorted(xs)
    if len(xs) == 1: return xs[0]
    k = (len(xs) - 1) * q; i = int(k); j = min(i + 1, len(xs) - 1)
    return xs[i] + (xs[j] - xs[i]) * (k - i)

def bias(job):
    if not os.path.exists(SC): return None
    errs = [json.loads(l)["err_min_p50"] for l in open(SC) if l.strip() and json.loads(l).get("job") == job]
    return statistics.median(errs) if errs else None

def forecast(samples, total, window_min, job):
    now = samples[-1]["ts"]; last = samples[-1]; first = samples[0]
    rem = total - last["done"]; notes = []
    if rem <= 0: return {"remaining": 0, "eta_p10": now, "eta_p50": now, "eta_p90": now, "notes": ["DONE by unit count"]}
    seg = [(b["done"] - a["done"]) / (b["ts"] - a["ts"]) for a, b in zip(samples, samples[1:]) if b["ts"] > a["ts"]]
    win = [s for s in samples if s["ts"] >= now - window_min * 60]
    if len(win) < 2: win = samples[-2:]
    rwin = (win[-1]["done"] - win[0]["done"]) / max(win[-1]["ts"] - win[0]["ts"], 1)
    rall = (last["done"] - first["done"]) / max(now - first["ts"], 1)
    recent = seg[-max(3, len(win) - 1):] if seg else [rwin]
    lo, mid, hi = pct(recent, .10), rwin, pct(recent, .90)
    rates = sorted(r for r in (lo, mid, hi, rall) if r > 0)
    if not rates or mid <= 0:
        return {"remaining": rem, "eta_p10": None, "eta_p50": None, "eta_p90": None, "notes": ["STALL: zero rate in window; ETA UNKNOWN"]}
    fast, slow = max(hi, mid * 1.10), min(min(x for x in (lo, mid, rall) if x > 0), mid * 0.90)  # >=+-10% floor
    e10, e50, e90 = now + rem / fast, now + rem / mid, now + rem / slow
    if rall > 0 and mid < 0.8 * rall: notes.append("SLOWDOWN: recent rate %.0f%% of overall" % (100 * mid / rall))
    if rall > 0 and mid > 1.25 * rall: notes.append("SPEEDUP: recent rate %.0f%% of overall (range widened)" % (100 * mid / rall))
    if len(seg) >= 1 and seg[-1] <= 0: notes.append("STALL: last interval made no progress")
    if now - samples[-2]["ts"] > 3 * statistics.median([b["ts"] - a["ts"] for a, b in zip(samples, samples[1:])] or [1]):
        notes.append("GAP: sample interval irregular")
    pp = last.get("proxy_pct")
    if pp is not None:
        wp = 100.0 * last["done"] / total
        if abs(pp - wp) >= 5: notes.append("PROXY DIVERGES: proxy %.2f%% vs work %.2f%% (trust work units)" % (pp, wp))
    b = bias(job)
    if b is not None: notes.append("past bias for job %s: median P50 error %+.1f min (positive = finished later than forecast)" % (job, b))
    return {"remaining": rem, "rate_win_per_min": mid * 60, "rate_all_per_min": rall * 60,
            "eta_p10": e10, "eta_p50": e50, "eta_p90": e90, "notes": notes}

def append_chain(path, rec):
    prev = ZERO
    if os.path.exists(path):
        lines = [l for l in open(path) if l.strip()]
        if lines: prev = json.loads(lines[-1])["hash"]
    if "config" not in rec:
        try:
            import qgate; rec["config"] = qgate.config(HOME)
        except Exception as e: rec["config"] = {"manifest_hash": "UNKNOWN", "error": e.__class__.__name__}
    rec["prev"] = prev
    rec["hash"] = hashlib.sha256((prev + json.dumps(rec, sort_keys=True)).encode()).hexdigest()
    with open(path, "a") as f: f.write(json.dumps(rec, sort_keys=True) + "\n")

def verify(path):
    prev = ZERO; n = 0
    for l in open(path):
        if not l.strip(): continue
        r = json.loads(l)
        if "rotated_from_head" in r: prev = r["rotated_from_head"]; continue
        h = r.pop("hash")
        if r["prev"] != prev or hashlib.sha256((prev + json.dumps(r, sort_keys=True)).encode()).hexdigest() != h:
            return "BREAK at record %d" % (n + 1)
        prev = h; n += 1
    return "OK %d records head %s" % (n, prev[:16])

def show(job, unit, total, s, fc, proxy_eta):
    print("AGAPE-ETA  job=%s  unit=%s" % (job, unit))
    print("as of      %s" % fts(s["ts"]))
    print("done       %d / %d %s (%.2f%%)" % (s["done"], total, unit, 100 * s["done"] / total))
    print("remaining  %d %s" % (fc["remaining"], unit))
    if fc.get("rate_win_per_min"): print("rate       window %.0f/min  overall %.0f/min" % (fc["rate_win_per_min"], fc["rate_all_per_min"]))
    for k in ("p10", "p50", "p90"):
        t = fc["eta_" + k]
        print("ETA %s    %s" % (k.upper(), "UNKNOWN" if t is None else "%s  (+%.0f min)" % (fts(t), (t - s["ts"]) / 60)))
    if proxy_eta: print("log says   %s" % proxy_eta)
    for n in fc["notes"]: print("NOTE       " + n)

def cmd_watch(a):
    samples = load(a.log, a.regex or DEF_RE)
    if a.at: samples = [s for s in samples if s["ts"] <= pts(a.at + ":00" if len(a.at) == 16 else a.at)]
    if len(samples) < 2: print("UNKNOWN: fewer than 2 samples"); return 2
    total = a.total or (float(samples[-1]["total"]) if samples[-1].get("total") else None)
    if not total: print("UNKNOWN: no total"); return 2
    fc = forecast(samples, total, a.window_min, a.job)
    proxy_eta = None
    if a.proxy_eta_regex:
        for line in open(a.log, errors="replace"):
            m = re.search(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", line)
            if m and pts(m.group(1)) <= samples[-1]["ts"]:
                e = re.search(a.proxy_eta_regex, line)
                if e: proxy_eta = e.group(0)
    show(a.job, a.unit, total, samples[-1], fc, proxy_eta)
    if not a.no_record:
        append_chain(FC, {"job": a.job, "unit": a.unit, "total": total, "as_of": samples[-1]["ts"], "done": samples[-1]["done"],
                          "eta_p10": fc["eta_p10"], "eta_p50": fc["eta_p50"], "eta_p90": fc["eta_p90"], "notes": fc["notes"],
                          "log_eta": proxy_eta, "made_at": time.time()})
    return 0

def cmd_score(a):
    fin = pts(a.finished); n = 0
    for l in open(FC):
        r = json.loads(l)
        if r.get("job") != a.job or r.get("eta_p50") is None: continue
        err = (fin - r["eta_p50"]) / 60; inside = r["eta_p10"] <= fin <= r["eta_p90"]
        append_chain(SC, {"job": a.job, "forecast_hash": r["hash"], "as_of": r["as_of"], "finished": fin,
                          "err_min_p50": round(err, 1), "inside_range": inside})
        print("%s  P50 err %+7.1f min  inside P10-P90: %s" % (fts(r["as_of"]), err, "YES" if inside else "NO")); n += 1
    print("scored %d forecasts" % n)

def cmd_report(a):
    for p in (FC, SC):
        print("%-16s %s" % (os.path.basename(p), verify(p) if os.path.exists(p) else "absent"))
    if os.path.exists(SC):
        by = {}
        for l in open(SC):
            r = json.loads(l)
            if "job" in r and "err_min_p50" in r: by.setdefault(r["job"], []).append(r)
        for j, rs in by.items():
            print("job %-20s n=%d  median P50 err %+.1f min  hit-rate %d/%d" % (j, len(rs),
                  statistics.median(r["err_min_p50"] for r in rs), sum(r["inside_range"] for r in rs), len(rs)))

def main():
    p = argparse.ArgumentParser(); sp = p.add_subparsers(dest="c", required=True)
    w = sp.add_parser("watch"); w.add_argument("log"); w.add_argument("--unit", default="units"); w.add_argument("--total", type=float)
    w.add_argument("--regex"); w.add_argument("--job", default="default"); w.add_argument("--window-min", type=float, default=15)
    w.add_argument("--at"); w.add_argument("--no-record", action="store_true"); w.add_argument("--proxy-eta-regex", default=r"ETA [\d.]+h")
    s = sp.add_parser("score"); s.add_argument("--job", required=True); s.add_argument("--finished", required=True)
    sp.add_parser("report")
    a = p.parse_args()
    return {"watch": cmd_watch, "score": cmd_score, "report": cmd_report}[a.c](a) or 0
if __name__ == "__main__": sys.exit(main())
