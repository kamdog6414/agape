#!/usr/bin/env python3
"""agape-eta runner (headless, stdlib, no LLM). Called by timer:  python3 eta_run.py run [--jobs jobs.json]
python3 eta_run.py aggregate <status.json> [...]   (read-only table)
jobs.json: {"node": "...", "jobs": [ {job, kind, ...} ]}
 kind=log    : path, regex (named groups ts, done [, proxy_pct]), unit, total | total_regex, done_regex (completion line, group ts)
 kind=window : start, end ("YYYY-MM-DD HH:MM:SS" local) -> unit=seconds of window elapsed
 kind=state  : path, done_regex, last-line status only (no units -> ETA UNKNOWN)
 kind=count  : path, regex (group ts) counts matching events; total optional (rate only if absent)
 kind=adb    : serial, cmd (read-only shell cmd), unit=lines of output (probe only)
 kind=file   : path, total (bytes) -> growth of a file's size (DONE when size >= total)
 kind=process: pid, match (substring of /proc/PID/cmdline), path (file being read) | total -> /proc/PID/io rchar vs size;
               DONE when the pid is gone (finish = extrapolated, clamped to [last seen alive, now])
 any job may set cal_kind (db-build, file-copy, sha-hash, sqlite-check, ingest, ...) for learning (learn.py)."""
import os, sys, re, json, time, subprocess
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import qgate  # config gate: verify code vs QUALIFIED.json BEFORE importing eta/learn
if sys.argv[1:2] == ["run"]: QINFO = qgate.gate_or_exit(HERE)
elif sys.argv[1:2] == ["gate"]:
    _ok, _i = qgate.check(HERE); print(_i["state"], _i.get("manifest_hash"), "; ".join(_i["why"])); sys.exit(0 if _ok else 1)
elif sys.argv[1:2] == ["qualify"]: sys.exit(qgate.qualify(sys.argv[2:], HERE))
import eta, learn
SAMP = os.path.join(HERE, "samples"); STATUS = os.path.join(HERE, "status.json"); RUNLOG = os.path.join(HERE, "run.log")
MAXF = 1_000_000

def rotate(path):
    if os.path.exists(path) and os.path.getsize(path) > MAXF:
        os.replace(path, path + ".1")  # one generation kept; chain continues from .1 head
        last = [l for l in open(path + ".1") if l.strip()][-1]
        with open(path, "w") as f: f.write(json.dumps({"rotated_from_head": json.loads(last)["hash"], "hash": json.loads(last)["hash"], "prev": json.loads(last)["prev"]}, sort_keys=True) + "\n")

def trim(path, keep=2000):
    if os.path.exists(path):
        L = open(path).readlines()
        if len(L) > keep:
            with open(path + ".tmp", "w") as f: f.writelines(L[-keep:])
            os.replace(path + ".tmp", path)

def addsample(job, s):
    os.makedirs(SAMP, exist_ok=True); p = os.path.join(SAMP, job + ".jsonl")
    last = None
    if os.path.exists(p):
        L = open(p).readlines()
        if L: last = json.loads(L[-1])
    if not last or s["ts"] > last["ts"]:
        with open(p, "a") as f: f.write(json.dumps(s) + "\n")
    trim(p); return eta.load(p, r"$^")

def scored(job):
    if not os.path.exists(eta.SC): return False
    return any(json.loads(l).get("job") == job for l in open(eta.SC) if l.strip() and "job" in l)

def autoscore(job, fin, kind=None, node=None, fin_note=None):
    if not os.path.exists(eta.FC): return None
    done = set(json.loads(l).get("forecast_hash") for l in open(eta.SC) if l.strip()) if os.path.exists(eta.SC) else set()
    n = 0; errs = []
    for l in open(eta.FC):
        r = json.loads(l)
        if r.get("job") != job or r.get("eta_p50") is None or "hash" not in r: continue
        if kind: learn.score(r, fin, kind, node, source="eta_run autoscore", fin_note=fin_note)
        if r["hash"] in done: continue
        err = (fin - r["eta_p50"]) / 60; inside = r["eta_p10"] <= fin <= r["eta_p90"]
        eta.append_chain(eta.SC, {"job": job, "forecast_hash": r["hash"], "as_of": r["as_of"], "finished": fin, "err_min_p50": round(err, 1), "inside_range": inside})
        n += 1; errs.append((err, inside))
    return n, errs

def do_job(j, now):
    k = j["kind"]; st = {"job": j["job"], "kind": k, "unit": j.get("unit", ""), "state": "RUNNING"}
    fin = None
    if k == "window":
        a, b = eta.pts(j["start"]), eta.pts(j["end"]); tot = b - a; d = max(0, min(now, b) - a)
        st.update(done=d, total=tot, unit="seconds", eta_p10=b, eta_p50=b, eta_p90=b, notes=["fixed window; ETA is the declared close"])
        if now < a: st["state"] = "BEFORE"
        if now >= b: st["state"] = "DONE"; fin = b
        return st, fin, None
    if k == "adb":
        try:
            o = subprocess.run(["adb", "-s", j["serial"], "shell", j["cmd"]], capture_output=True, text=True, timeout=20)
            n = len([x for x in o.stdout.splitlines() if x.strip()]) if o.returncode == 0 else None
        except Exception as e: n = None
        st.update(done=n, total=None, state="REACHABLE" if n is not None else "UNREACHABLE",
                  notes=["read-only adb probe; no progress unit on device -> ETA UNKNOWN"]); st["eta_p50"] = None
        return st, None, None
    if k in ("file", "process"): return growth_job(j, st, now)
    p = os.path.expanduser(j["path"])
    if not os.path.exists(p): st.update(state="UNKNOWN", notes=["log missing: " + p]); return st, None, None
    lines = eta.tail_lines(p)
    if j.get("done_regex"):
        for ln in lines:
            m = re.search(j["done_regex"], ln)
            if m: fin = eta.pts(m.group("ts")); st["state"] = "DONE"
    st["last_line"] = (lines[-1][:160] if lines else "")
    if k == "state":
        if st["state"] != "DONE": st["state"] = "UNKNOWN"
        st.update(eta_p50=None, notes=["no work units in log -> ETA UNKNOWN"]); return st, fin, None
    total = j.get("total")
    if j.get("total_regex"):
        for ln in lines:
            m = re.search(j["total_regex"], ln)
            if m: total = float(m.group(1))
    if k == "count":
        ts = [eta.pts(m.group("ts")) for m in (re.search(j["regex"], ln) for ln in lines) if m]
        if not ts: st.update(state="UNKNOWN", notes=["no events"]); return st, fin, None
        samples = [{"ts": t, "done": i + 1, "total": None, "proxy_pct": None} for i, t in enumerate(ts)]
    else:
        got = eta.load(p, j["regex"])
        for s in got: addsample(j["job"], s)
        samples = eta.load(os.path.join(SAMP, j["job"] + ".jsonl"), r"$^") if got else []
    if len(samples) < 2: st.update(state="UNKNOWN", notes=["<2 samples"]); return st, fin, None
    last = samples[-1]; st.update(done=last["done"], total=total, as_of=last["ts"])
    if not total:
        win = [s for s in samples if s["ts"] >= last["ts"] - 3600] or samples[-2:]
        r = (win[-1]["done"] - win[0]["done"]) / max(win[-1]["ts"] - win[0]["ts"], 1) * 3600
        st.update(rate_per_hour=round(r, 2), eta_p50=None, notes=["no total declared -> rate only, ETA UNKNOWN"])
        if now - last["ts"] > 3 * 3600: st["notes"].append("STALL: no event for %.0f min" % ((now - last["ts"]) / 60))
        return st, fin, None
    fc = eta.forecast(samples, total, j.get("window_min", 15), j["job"])
    silent = (now - last["ts"]) / 60
    st.update(fc)
    if silent > 20 and st["state"] != "DONE":
        st["notes"] = fc["notes"] + ["STALL: log silent %.0f min" % silent]
        if silent > 60:
            st.update(state="STALLED", eta_p10=None, eta_p50=None, eta_p90=None); st["notes"].append("ETA UNKNOWN until progress resumes")
            return st, fin, None
    return st, fin, fc

def jobsamples(job):
    p = os.path.join(SAMP, job + ".jsonl")
    return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []

def growth_job(j, st, now):
    """file: size of path vs total.  process: /proc/PID/io rchar vs total (or size of path)."""
    k = j["kind"]; st["unit"] = "bytes"; node = j.get("_node")
    total = j.get("total")
    if not total and j.get("path") and os.path.exists(os.path.expanduser(j["path"])): total = float(os.path.getsize(os.path.expanduser(j["path"])))
    done = None; alive = True
    if k == "file":
        p = os.path.expanduser(j["path"])
        if os.path.exists(p): done = float(os.path.getsize(p))
        else: st.update(state="UNKNOWN", notes=["file missing: " + p]); return st, None, None
    else:
        pid = str(j["pid"])
        try:
            cmd = open("/proc/%s/cmdline" % pid, "rb").read().replace(b"\0", b" ").decode("utf-8", "replace")
            if j.get("match") and j["match"] not in cmd: raise OSError("pid reused")
            for ln in open("/proc/%s/io" % pid):
                if ln.startswith("rchar:"): done = float(ln.split()[1])
        except OSError: alive = False
    old = jobsamples(j["job"])
    if done is not None:
        addsample(j["job"], {"ts": now, "done": done, "total": total, "proxy_pct": None})
    S = jobsamples(j["job"])
    if k == "process" and not alive:
        prior_done = [x for x in S if x.get("state") == "DONE"]
        if prior_done: fin = prior_done[-1]["finished"]
        elif not S: st.update(state="UNKNOWN", notes=["pid %s not running and never seen alive -> finish UNKNOWN" % j["pid"]]); return st, None, None
        else:
            last = S[-1]; fin = now; note = "pid gone; finish clamped to [last seen alive %s, now]" % learn.iso(last["ts"])
            if len(S) >= 2 and total:
                r = (S[-1]["done"] - S[-2]["done"]) / max(S[-1]["ts"] - S[-2]["ts"], 1)
                if r > 0: fin = min(max(last["ts"] + max(total - last["done"], 0) / r, last["ts"]), now)
            os.makedirs(SAMP, exist_ok=True)
            with open(os.path.join(SAMP, j["job"] + ".jsonl"), "a") as f: f.write(json.dumps({"ts": now, "done": last["done"], "state": "DONE", "finished": fin, "note": note}) + "\n")
            S = jobsamples(j["job"])
        st.update(state="DONE", done=total, total=total, eta_p10=fin, eta_p50=fin, eta_p90=fin, notes=["process ended; " + ([x for x in S if x.get("state") == "DONE"][-1].get("note", ""))])
        st["fin_lo"] = [x for x in S if "state" not in x][-1]["ts"] if [x for x in S if "state" not in x] else None
        return st, fin, None
    if done is None or not total: st.update(state="UNKNOWN", done=done, total=total, notes=["no size/total"]); return st, None, None
    st.update(done=done, total=total, as_of=now)
    S = [x for x in S if "state" not in x]
    if done >= total and k == "file":
        fin = S[0]["ts"] if len(S) == 1 else next((x["ts"] for x in S if x["done"] >= total), now)
        st.update(state="DONE", eta_p10=fin, eta_p50=fin, eta_p90=fin, notes=["file reached total"]); return st, fin, None
    if len(S) >= 2 and S[-1]["done"] > S[0]["done"]:
        fc = eta.forecast([{"ts": x["ts"], "done": x["done"], "proxy_pct": None} for x in S], total, j.get("window_min", 15), j["job"])
        st.update(fc); return st, None, fc
    pr, n = learn.prior_rate(node, j.get("cal_kind", k))
    if pr:
        rem = (total - done) / pr
        fc = {"remaining": total - done, "rate_win_per_min": pr * 60, "rate_all_per_min": pr * 60,
              "eta_p10": now + rem * 0.75, "eta_p50": now + rem, "eta_p90": now + rem * 1.5,
              "notes": ["PRIOR: first sample; learned %s rate %.0f B/s (n=%d) on %s" % (j.get("cal_kind", k), pr, n, node)]}
        st.update(fc); return st, None, fc
    st.update(notes=["first sample, no learned prior -> ETA UNKNOWN"]); return st, None, None

def finish_obs(j, st, fin, node, ck):
    """OBS throughput for a finished job from its own samples (start = first sample or job 'start')."""
    S = [x for x in jobsamples(j["job"]) if "state" not in x]
    start = eta.pts(j["start"]) if j.get("start") else None; d0 = 0.0
    if start is None and len(S) >= 2: start, d0 = S[0]["ts"], S[0]["done"]
    if start is None and j.get("path") and j["kind"] == "log":
        try:
            L = eta.load(os.path.expanduser(j["path"]), j["regex"])
            if len(L) >= 2: start, d0 = L[0]["ts"], L[0]["done"]
        except Exception: pass
    tot = st.get("total")
    learn.observe(node, ck, j["job"], start, fin, (tot - d0) if tot else None, st.get("unit") or "units", "eta_run finish_obs",
                  note=None if start is None else "start = %s" % ("declared" if j.get("start") else "first observed sample (lower bound on throughput if work began earlier)"))

def run(jobsfile):
    cfg = json.load(open(jobsfile)); now = time.time(); out = []
    rotate(eta.FC); rotate(eta.SC)
    node = cfg.get("node")
    for j in cfg["jobs"]:
        try:
            j["_node"] = node; ck = j.get("cal_kind") or j["kind"]
            st, fin, fc = do_job(j, now)
            if fc and st["state"] != "DONE":
                fc, lab = learn.adjust(fc, ck, now); st.update(fc)
            st["cal_kind"] = ck; st["cal"] = learn.cal_label(ck)
            S2 = [x for x in jobsamples(j["job"]) if "state" not in x][-2:]
            if len(S2) == 2: st["last2"] = [[x["ts"], x["done"]] for x in S2]
            if st.get("rate_win_per_min"): st["rate_per_s"] = st["rate_win_per_min"] / 60.0
            prevfc = [json.loads(l) for l in open(eta.FC) if '"%s"' % j["job"] in l][-1:] if os.path.exists(eta.FC) else []
            if fc and st["state"] != "DONE" and not (prevfc and prevfc[0].get("as_of") == st.get("as_of")):
                eta.append_chain(eta.FC, {"job": j["job"], "unit": st["unit"], "total": st["total"], "as_of": st["as_of"], "done": st["done"],
                    "eta_p10": fc["eta_p10"], "eta_p50": fc["eta_p50"], "eta_p90": fc["eta_p90"], "notes": fc["notes"], "made_at": now,
                    "raw_p10": fc.get("raw_p10"), "raw_p50": fc.get("raw_p50"), "raw_p90": fc.get("raw_p90"), "cal_kind": ck})
            if fin is not None:
                r = autoscore(j["job"], fin, ck, node, st.get("fin_note")); st["finished"] = fin
                if r and r[0]: st["scored"] = "%d forecasts" % r[0]
                finish_obs(j, st, fin, node, ck)
        except Exception as e:
            st = {"job": j.get("job"), "state": "ERROR", "notes": [repr(e)[:200]]}
        out.append(st)
    try: learn.calibrate_all(node)
    except Exception as e: out.append({"job": "learn", "state": "ERROR", "notes": [repr(e)[:200]]})
    doc = {"node": cfg.get("node"), "generated": now, "status": "QUALIFIED", "qualification": QINFO, "config": qgate.config(HERE), "jobs": out}
    with open(STATUS + ".tmp", "w") as f: json.dump(doc, f, indent=1)
    os.replace(STATUS + ".tmp", STATUS)
    txt = render(doc)
    with open(RUNLOG, "a") as f: f.write(txt + "\n")
    trim(RUNLOG, 3000)
    print(txt)

def fm(t): return "UNKNOWN" if not t else time.strftime("%m-%d %H:%M %Z", time.localtime(t))
def render(doc):
    L = ["AGAPE-ETA node=%s at %s %s manifest %s" % (doc.get("node"), fm(doc["generated"]), doc.get("status", "UNKNOWN"), str((doc.get("config") or {}).get("manifest_hash", "UNKNOWN"))[:16])]
    for s in doc["jobs"]:
        done = s.get("done"); tot = s.get("total")
        prog = "%s/%s %s" % (int(done) if done is not None else "?", int(tot) if tot else "?", s.get("unit", ""))
        L.append("  %-20s %-11s %-36s P10 %s | P50 %s | P90 %s" % (s.get("job"), s.get("state"), prog, fm(s.get("eta_p10")), fm(s.get("eta_p50")), fm(s.get("eta_p90"))))
        for n in s.get("notes", []) or []: L.append("      note: " + n)
        if s.get("cal") and s.get("cal") != "cal: none": L.append("      " + s["cal"] + " (" + str(s.get("cal_kind")) + ")")
        if s.get("scored"): L.append("      scored: " + s["scored"])
    return "\n".join(L)

def aggregate(files):
    for p in files:
        try:
            d = json.load(open(p)); age = (time.time() - d["generated"]) / 60
            print(render(d) + ("\n      STALE: status %.0f min old" % age if age > 15 else ""))
        except Exception as e: print("AGAPE-ETA %s UNKNOWN (%s)" % (p, e.__class__.__name__))

if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "run": run(a[2] if len(a) > 2 and a[1] == "--jobs" else os.path.join(HERE, "jobs.json"))
    elif a and a[0] == "aggregate": aggregate(a[1:])
    else: print(__doc__)
