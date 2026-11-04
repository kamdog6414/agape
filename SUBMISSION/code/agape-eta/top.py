#!/usr/bin/env python3
"""eta top - live black/white ETA view (stdlib only, read-only; additive to eta.py).
Reads ./status.json + ./peers/*.json; optional --file PATH:TOTALBYTES[:NAME] (repeatable)
or --remote-file 'CMD' sampling via a shell command that prints a byte count."""
import sys, os, json, time, glob, argparse, subprocess, collections
HERE = os.path.dirname(os.path.abspath(__file__))
WIN = 30.0
hist = collections.defaultdict(collections.deque)  # key -> (t, done)

def hms(s):
    if s is None: return "UNKNOWN"
    s = int(max(0, s)); return "%d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)

def sample(key, t, done):
    d = hist[key]
    if not d or d[-1][1] != done or t - d[-1][0] >= 1: d.append((t, done))
    while d and t - d[0][0] > WIN: d.popleft()

def rate(key):
    d = hist[key]
    if len(d) < 2 or d[-1][0] - d[0][0] <= 0: return None
    return (d[-1][1] - d[0][1]) / (d[-1][0] - d[0][0])

def status_rate(jb):
    """rate from the job's own rate field, else from its last two status samples (per second)."""
    if jb.get("rate_per_s"): return float(jb["rate_per_s"])
    if jb.get("rate_win_per_min"): return float(jb["rate_win_per_min"]) / 60.0
    if jb.get("rate_per_hour"): return float(jb["rate_per_hour"]) / 3600.0
    l2 = jb.get("last2")
    if l2 and len(l2) == 2 and l2[1][0] > l2[0][0]: return (l2[1][1] - l2[0][1]) / (l2[1][0] - l2[0][0])
    return None

def load_status():
    rows = []
    files = [os.path.join(HERE, "status.json")] + sorted(glob.glob(os.path.join(HERE, "peers", "*.json")))
    for f in files:
        try: j = json.load(open(f))
        except Exception: continue
        for jb in j.get("jobs", []):
            rows.append(dict(name=jb.get("job"), node=j.get("node", "?"), state=("UNKNOWN" if jb.get("state") in (None, "", "?", "STATE") else jb.get("state")),
                done=jb.get("done"), total=jb.get("total"), unit=jb.get("unit", ""),
                p10=jb.get("eta_p10"), p50=jb.get("eta_p50"), p90=jb.get("eta_p90"), kind=jb.get("kind"), cal=jb.get("cal") or "cal: none",
                srate=status_rate(jb)))
    return rows

def file_row(spec, now, remote=None):
    parts = spec.split(":")
    path, total = parts[0], float(parts[1]); name = parts[2] if len(parts) > 2 else os.path.basename(path)
    try:
        if remote:
            size = float(subprocess.run(remote, shell=True, capture_output=True, text=True, timeout=10).stdout.strip())
        else:
            size = float(os.path.getsize(os.path.expanduser(path)))
    except Exception:
        return dict(name=name, node="remote" if remote else "local", state="NOFILE", done=None, total=total, unit="bytes", kind="file")
    key = "file:" + name; sample(key, now, size); r = rate(key)
    row = dict(name=name, node="remote" if remote else "local", done=size, total=total, unit="bytes", kind="file")
    if size >= total: row.update(state="DONE", p10=now, p50=now, p90=now)
    elif r and r > 0:
        rem = (total - size) / r
        row.update(state="RUNNING", p10=now + rem * 0.8, p50=now + rem, p90=now + rem * 1.5)
    else: row.update(state="WAITING" if len(hist[key]) < 2 else "STALLED", p10=None, p50=None, p90=None)
    row["rate"] = r
    return row

def qual_line():
    """QUAL header: live read-only gate check of this dir + last run status of this node and peers."""
    try:
        sys.path.insert(0, HERE); import qgate
        ok, i = qgate.check(HERE); s = "QUAL %s manifest %s" % (i["state"], (i.get("manifest_hash") or "none")[:16])
        if not ok: s += " (%s)" % "; ".join(i["why"][:2])
    except Exception as e: s = "QUAL UNKNOWN (%s)" % e.__class__.__name__
    parts = []
    for f in [os.path.join(HERE, "status.json")] + sorted(glob.glob(os.path.join(HERE, "peers", "*.json"))):
        try: j = json.load(open(f)); parts.append("%s=%s/%s" % (j.get("node", "?"), j.get("status", "UNKNOWN"), str((j.get("config") or {}).get("manifest_hash", "?"))[:8]))
        except Exception: pass
    return s + "  | last run: " + (" ".join(parts) or "none")

def frame(a, now):
    rows = load_status()
    for r in rows:
        if r["done"] is not None:
            sample(r["node"] + "/" + r["name"], now if r["kind"] == "window" else now, r["done"])
            own = rate(r["node"] + "/" + r["name"])
            r.setdefault("rate", own if own else r.get("srate"))  # own 30s samples only when they move
    for spec in a.file or []: rows.append(file_row(spec, now))
    for spec in a.remote_file or []:
        cmd, rest = spec.split("|", 1); rows.append(file_row(rest, now, remote=cmd))
    wj = max([14] + [len(str(r["name"])) for r in rows]); wn = max([8] + [len(str(r["node"])) for r in rows])
    ws = max([8] + [len(str(r["state"])) for r in rows])
    out = ["eta top  %s   refresh %.0fs   rate=own %ds window   (q/Ctrl-C quits)" % (time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(now)), a.interval, WIN),
           qual_line(),
           "%-*s %-*s %-*s %23s %6s %12s %10s  %-21s %s" % (wj, "JOB", wn, "NODE", ws, "STATE", "DONE/TOTAL", "%", "RATE/s", "P50 IN", "P10..P90 IN", "CAL")]
    for r in rows:
        d, t = r["done"], r["total"]
        dt = "%s/%s" % ("?" if d is None else "%.0f" % d, "?" if not t else "%.0f" % t)
        pc = "%5.1f" % (100.0 * d / t) if d is not None and t else "  ?"
        rt = ("%.2f" % r["rate"] if abs(r["rate"]) >= 1 or r["rate"] == 0 else "%.3g" % r["rate"]) if r.get("rate") is not None else "--"
        p = lambda k: None if r.get(k) is None else r[k] - now
        out.append("%-*s %-*s %-*s %23s %6s %12s %10s  %-21s %s" % (wj, r["name"], wn, r["node"], ws, r["state"],
                   dt[-23:], pc, rt, hms(p("p50")), "%s..%s" % (hms(p("p10")), hms(p("p90"))), r.get("cal", "cal: none")))
    if not rows: out.append("(no jobs found)")
    return "\n".join(out)

def main():
    ap = argparse.ArgumentParser(description="eta top: live ETA view")
    ap.add_argument("--once", action="store_true"); ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--file", action="append", help="PATH:TOTALBYTES[:NAME]")
    ap.add_argument("--remote-file", action="append", help="'SIZE_CMD|PATH:TOTALBYTES[:NAME]'")
    a = ap.parse_args()
    if a.once:
        frame(a, time.time()); time.sleep(a.interval); print(frame(a, time.time())); return
    try:
        sys.stdout.write("\x1b[?25l")
        while True:
            f = frame(a, time.time())
            sys.stdout.write("\x1b[H\x1b[2J" + f + "\n"); sys.stdout.flush()
            time.sleep(a.interval)
    except KeyboardInterrupt: pass
    finally: sys.stdout.write("\x1b[?25h\n")

if __name__ == "__main__": main()
