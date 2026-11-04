#!/usr/bin/env python3
"""agape-eta config gate (stdlib only). "A run must run the configuration that was qualified."
QUALIFIED.json = {"v":1, "tool_version", "files": {relpath: sha256}, "manifest_hash", ...node-local suite info}
manifest_hash = sha256(canonical JSON of {"files", "tool_version"})  -> identical on every node running identical code.
Code covered: every *.py in the tool dir + seed-*.json + qualfix/* fixtures. NOT covered: ledgers (*.jsonl), status.json, run.log, jobs.json, *.bak-*.
Ledger qualification.jsonl: append-only, FAILS-LEDGER hash convention (canonical JSON, prev_hash/hash, seq),
verdict 0 HOLDS / 1 FAIL / 2 UNKNOWN.
  python3 eta_run.py qualify [--unqualified-since "YYYY-MM-DD HH:MM:SS" --reason TEXT]
  python3 eta_run.py gate        (read-only check, exit 0 qualified / 1 not)"""
import os, sys, json, glob, time, hashlib, platform, subprocess, tempfile, shutil
from datetime import datetime
TOOL_VERSION = "agape-eta 0.4.0-gate"
GEN = "0" * 64
HERE = os.path.dirname(os.path.abspath(__file__))
QF = os.path.join(HERE, "QUALIFIED.json"); QL = os.path.join(HERE, "qualification.jsonl")

def canon(o): return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
def iso(t=None): return datetime.fromtimestamp(time.time() if t is None else t).astimezone().isoformat(timespec="seconds")

def code_files(d=HERE):
    fs = [os.path.basename(p) for p in glob.glob(os.path.join(d, "*.py"))]
    fs += [os.path.basename(p) for p in glob.glob(os.path.join(d, "seed-*.json"))]   # suite fixture
    fs += ["qualfix/" + os.path.basename(p) for p in glob.glob(os.path.join(d, "qualfix", "*")) if os.path.isfile(p)]
    return sorted(fs)
def current(d=HERE): return {f: sha_file(os.path.join(d, f)) for f in code_files(d)}
def manifest_hash(files, tv=TOOL_VERSION): return hashlib.sha256(canon({"files": files, "tool_version": tv}).encode()).hexdigest()

def check(d=HERE):
    """-> (ok, info). Read-only."""
    q = os.path.join(d, "QUALIFIED.json")
    if not os.path.exists(q): return False, {"state": "UNQUALIFIED", "why": ["QUALIFIED.json absent"], "manifest_hash": None}
    try: m = json.load(open(q))
    except Exception as e: return False, {"state": "UNQUALIFIED", "why": ["QUALIFIED.json unreadable: %s" % e.__class__.__name__], "manifest_hash": None}
    why = []; cur = current(d); want = m.get("files", {})
    if manifest_hash(want, m.get("tool_version")) != m.get("manifest_hash"): why.append("manifest_hash does not match its own file list")
    if m.get("tool_version") != TOOL_VERSION: why.append("tool_version %s != running %s" % (m.get("tool_version"), TOOL_VERSION))
    for f in sorted(set(want) | set(cur)):
        if f not in cur: why.append("missing %s" % f)
        elif f not in want: why.append("unlisted code file %s sha %s" % (f, cur[f][:16]))
        elif cur[f] != want[f]: why.append("sha mismatch %s want %s have %s" % (f, want[f][:16], cur[f][:16]))
    return (not why), {"state": "QUALIFIED" if not why else "UNQUALIFIED", "why": why, "manifest_hash": m.get("manifest_hash"),
                       "qualified_at": m.get("qualified_at")}

def node_name(d=HERE):
    try: return json.load(open(os.path.join(d, "jobs.json"))).get("node") or platform.node()
    except Exception: return os.environ.get("ETA_NODE") or platform.node() or "UNKNOWN"
def os_release():
    try:
        for l in open("/etc/os-release"):
            if l.startswith("PRETTY_NAME="): return "%s; kernel %s" % (l.split("=", 1)[1].strip().strip('"'), platform.release())
    except OSError: pass
    return platform.platform() or "UNKNOWN"
_CFG = None
def config(d=HERE):
    """config pin carried by every new record."""
    global _CFG
    if _CFG is None:
        ok, info = check(d)
        _CFG = {"manifest_hash": info["manifest_hash"] if ok else "UNQUALIFIED", "node": node_name(d),
                "python": platform.python_version(), "os_release": os_release(), "tool_version": TOOL_VERSION}
    return dict(_CFG)

# ---------- ledger ----------
def records(p=QL): return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if os.path.exists(p) else []
def rec_hash(r): return hashlib.sha256(canon({k: v for k, v in r.items() if k != "hash"}).encode("utf-8")).hexdigest()
def append(fields, p=QL):
    rs = records(p); prev = rs[-1] if rs else None
    r = dict(fields); r.update(v=1, seq=prev["seq"] + 1 if prev else 1, prev_hash=prev["hash"] if prev else GEN)
    r.setdefault("ts", iso()); r["hash"] = rec_hash(r)
    with open(p, "a", encoding="utf-8") as f: f.write(canon(r) + "\n")
    return r
def verify(p=QL):
    prev = GEN
    for i, r in enumerate(records(p), 1):
        if r.get("prev_hash") != prev or rec_hash(r) != r.get("hash") or r.get("seq") != i: return "BREAK at seq %d" % i
        prev = r["hash"]
    return "OK %d records head %s" % (len(records(p)), prev[:16])

def gate_or_exit(d=HERE):
    """Called by eta_run.py run BEFORE eta/learn are imported. On mismatch: FAIL record + status UNQUALIFIED, no forecasts, exit 3."""
    ok, info = check(d)
    if ok: return info
    cfg = config(d); now = time.time()
    append({"type": "GATE", "node": cfg["node"], "config": cfg,
            "claim": "code in %s matches QUALIFIED.json manifest %s" % (d, info["manifest_hash"]),
            "falsifier": "any listed code file sha256 differs, is missing, or an unlisted *.py/qualfix file exists => FAIL(1); manifest absent/unreadable => FAIL(1)",
            "verdict": 1, "why": info["why"][:40], "action": "run refused; no forecasts, scores or calibration written"}, os.path.join(d, "qualification.jsonl"))
    st = os.path.join(d, "status.json")
    doc = {"node": cfg["node"], "generated": now, "status": "UNQUALIFIED", "qualification": info, "config": cfg, "jobs": []}
    with open(st + ".tmp", "w") as f: json.dump(doc, f, indent=1)
    os.replace(st + ".tmp", st)
    with open(os.path.join(d, "run.log"), "a") as f:
        f.write("AGAPE-ETA node=%s at %s UNQUALIFIED - run refused: %s\n" % (cfg["node"], time.strftime("%m-%d %H:%M %Z"), "; ".join(info["why"][:5])))
    print("UNQUALIFIED: run refused\n  " + "\n  ".join(info["why"]))
    sys.exit(3)

# ---------- qualification suite ----------
SKIP = {"hash", "prev_hash", "seq", "ts", "v", "config"}
def suite(d=HERE):
    """Replay scored history and require identical recomputed results; verify every hash chain; run top.py --once."""
    sys.path.insert(0, d)
    import eta, learn
    R = []; ok = True
    def res(name, passed, detail):
        nonlocal ok
        R.append({"check": name, "verdict": 0 if passed is True else (2 if passed is None else 1), "detail": detail})
        if passed is not True: ok = False
    tmp = tempfile.mkdtemp(prefix="qual-")
    try:
        seed = json.load(open(os.path.join(d, "seed-20261104.json")))
        fix = [json.loads(l) for l in open(os.path.join(d, "qualfix", "wikidb-roach-forecasts.jsonl")) if l.strip()]
        # R1: recompute wikidb-roach forecasts from the fixture log (Roach LIVE.log copy)
        oldsc = eta.SC; eta.SC = os.path.join(tmp, "none.jsonl")
        log = os.path.join(d, "qualfix", "LIVE-copy-20261104T1005.log"); bad = []
        for r in fix:
            S = [s for s in eta.load(log, eta.DEF_RE) if s["ts"] <= r["as_of"]]
            fc = eta.forecast(S, r["total"], 15, r["job"])
            if any(fc[k] != r[k] for k in ("eta_p10", "eta_p50", "eta_p90")) or fc["notes"] != r["notes"] or S[-1]["done"] != r["done"]: bad.append(r["hash"][:16])
        eta.SC = oldsc
        res("R1 replay wikidb-roach forecasts from fixture log", not bad and len(fix) == 5, "%d/%d identical%s" % (len(fix) - len(bad), len(fix), (" BAD " + ",".join(bad)) if bad else ""))
        # forecasts index: fixture + seed + local forecasts.jsonl
        F = {r["hash"]: r for r in fix}
        for s in seed["scores"]: F.setdefault(s["fc"]["hash"], s["fc"])
        lf = os.path.join(d, "forecasts.jsonl")
        if os.path.exists(lf):
            for l in open(lf):
                if l.strip():
                    r = json.loads(l)
                    if "hash" in r: F.setdefault(r["hash"], r)
        # R2: every SCORE in calibration.jsonl recomputed with learn.score into a temp ledger
        cal = [r for r in learn.records(os.path.join(d, "calibration.jsonl"))]
        S = [r for r in cal if r.get("type") == "SCORE"]; n_ok = 0; bad = []; unk = []
        for r in S:
            fc = F.get(r.get("forecast_hash"))
            if fc is None: unk.append(r.get("job")); continue
            t = os.path.join(tmp, "c.jsonl")
            if os.path.exists(t): os.remove(t)
            n = learn.score(fc, r["finished"], r["kind"], r["node"], source=r["source"], fin_note=r.get("finish_note"), path=t)
            a = {k: v for k, v in n.items() if k not in SKIP}; b = {k: v for k, v in r.items() if k not in SKIP}
            if a == b: n_ok += 1
            else: bad.append("%s seq %s diff %s" % (r.get("job"), r.get("seq"), sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))))
        need = {"wikidb-roach": 5, "copy-wikidb-roach-to-sat": 1, "sha256-wikidb-roach-sat": 1}
        have = {j: sum(1 for r in S if r.get("job") == j) for j in need}
        miss = [j for j in need if have[j] < need[j]]
        res("R2 replay calibration SCOREs (wikidb-roach, SAT copy, SAT sha, + local)", (None if unk else True) if not bad and not miss else False,
            "%d/%d identical; required %s%s%s" % (n_ok, len(S), have, (" MISSING " + ",".join(miss)) if miss else "", (" BAD " + "; ".join(bad)) if bad else "")
            + ((" forecast not locatable (UNKNOWN): %s" % unk) if unk else ""))
        # R3: SCOREs must also match the seed's evidence (forecast+finish as cited)
        bad = []
        for s in seed["scores"]:
            m = [r for r in S if r.get("forecast_hash") == s["fc"]["hash"] and r.get("finished") == s["fin"] and r.get("node") == s["node"]]
            if not m: bad.append(s["fc"]["job"])
        res("R3 seed scores present with cited finish (incl. SAT copy, SAT sha)", not bad, "%d/%d present%s" % (len(seed["scores"]) - len(bad), len(seed["scores"]), (" MISSING " + ",".join(bad)) if bad else ""))
        # R4: OBS throughput recompute
        bad = []; nO = 0
        for r in cal:
            if r.get("type") != "OBS": continue
            nO += 1
            rate = (r["total"] / (r["finished"] - r["start"])) if (r.get("start") is not None and r.get("finished") and r.get("total") and r["finished"] > r["start"]) else None
            if (None if rate is None else round(rate, 3)) != r.get("rate_per_s"): bad.append("%s seq %s" % (r.get("job"), r.get("seq")))
        res("R4 replay OBS throughput", not bad, "%d/%d identical%s" % (nO - len(bad), nO, (" BAD " + ",".join(bad)) if bad else ""))
        # R5: eta-format scores.jsonl recompute
        sp = os.path.join(d, "scores.jsonl")
        if os.path.exists(sp):
            bad = []; ns = 0
            for l in open(sp):
                if not l.strip(): continue
                r = json.loads(l)
                if "forecast_hash" not in r: continue
                ns += 1; fc = F.get(r["forecast_hash"])
                if fc is None: bad.append("UNKNOWN fc " + r["forecast_hash"][:12]); continue
                if round((r["finished"] - fc["eta_p50"]) / 60, 1) != r["err_min_p50"] or (fc["eta_p10"] <= r["finished"] <= fc["eta_p90"]) != r["inside_range"]: bad.append(r["hash"][:12])
            res("R5 replay scores.jsonl", not bad, "%d/%d identical%s" % (ns - len(bad), ns, (" BAD " + ",".join(bad)) if bad else ""))
        else: res("R5 replay scores.jsonl", True, "absent on this node (nothing to replay)")
        # H: hash chains
        for name in ("forecasts.jsonl", "scores.jsonl"):
            p = os.path.join(d, name)
            if os.path.exists(p): v = eta.verify(p); res("H chain " + name, v.startswith("OK"), v)
        v = learn.verify(os.path.join(d, "calibration.jsonl")); res("H chain calibration.jsonl", v.startswith("OK"), v)
        if os.path.exists(os.path.join(d, "qualification.jsonl")): v = verify(os.path.join(d, "qualification.jsonl")); res("H chain qualification.jsonl", v.startswith("OK"), v)
        # T: top.py --once
        try:
            o = subprocess.run([sys.executable, "-B", os.path.join(d, "top.py"), "--once", "--interval", "0.2"], capture_output=True, text=True, timeout=60, cwd=d)
            hdr = [l for l in o.stdout.splitlines() if l.startswith("QUAL ")]
            res("T top.py --once", o.returncode == 0 and o.stdout.startswith("eta top") and bool(hdr), "rc=%d header=%r" % (o.returncode, hdr[0] if hdr else None))
        except Exception as e: res("T top.py --once", False, repr(e)[:200])
    except Exception as e:
        res("suite crashed", False, repr(e)[:300])
    finally: shutil.rmtree(tmp, ignore_errors=True)
    return ok, R

def qualify(argv, d=HERE):
    since = reason = None
    if "--unqualified-since" in argv: since = argv[argv.index("--unqualified-since") + 1]
    if "--reason" in argv: reason = argv[argv.index("--reason") + 1]
    files = current(d); mh = manifest_hash(files)
    ok, R = suite(d)
    for r in R: print("%-4s %-70s %s" % (["PASS", "FAIL", "UNKN"][r["verdict"]], r["check"], r["detail"]))
    node = node_name(d)
    base = {"node": node, "manifest_hash_candidate": mh, "files": files, "suite": R,
            "claim": "code with manifest %s passes the qualification suite on %s" % (mh, node),
            "falsifier": "any suite check not PASS => FAIL(1), no QUALIFIED.json written"}
    if not ok:
        append(dict(base, type="QUALIFY", verdict=1, action="QUALIFIED.json NOT written"), os.path.join(d, "qualification.jsonl"))
        print("QUALIFY FAIL: QUALIFIED.json not written"); return 1
    q = os.path.join(d, "QUALIFIED.json")
    if os.path.exists(q): shutil.copy2(q, q + ".bak-" + time.strftime("%Y%m%dT%H%M%S"))
    global _CFG; _CFG = None
    doc = {"v": 1, "tool_version": TOOL_VERSION, "files": files, "manifest_hash": mh, "node": node, "qualified_at": iso(),
           "python": platform.python_version(), "os_release": os_release(), "suite": [{"check": r["check"], "verdict": r["verdict"]} for r in R]}
    with open(q + ".tmp", "w") as f: json.dump(doc, f, indent=1, sort_keys=True)
    os.replace(q + ".tmp", q)
    _CFG = None; cfg = config(d)
    rec = append(dict(base, type="QUALIFY", verdict=0, config=cfg, action="QUALIFIED.json written"), os.path.join(d, "qualification.jsonl"))
    doc["qualify_record_hash"] = rec["hash"]
    with open(q + ".tmp", "w") as f: json.dump(doc, f, indent=1, sort_keys=True)
    os.replace(q + ".tmp", q)
    if since: note_unqualified(since, reason or "", d, cfg)
    print("QUALIFY PASS manifest %s on %s" % (mh, node)); return 0

def note_unqualified(since, reason, d, cfg):
    """Append (never rewrite) a NOTE to each existing ledger listing records written at/after `since` that ran unqualified."""
    sys.path.insert(0, d); import eta, learn
    t0 = eta.pts(since); now = time.time(); listed = {}
    def L(p): return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []
    fp, sp, cp = (os.path.join(d, x) for x in ("forecasts.jsonl", "scores.jsonl", "calibration.jsonl"))
    listed["forecasts.jsonl"] = [r["hash"] for r in L(fp) if "hash" in r and r.get("made_at", 0) >= t0]
    listed["scores.jsonl"] = [r["hash"] for r in L(sp) if "hash" in r and r.get("finished", 0) >= t0]   # written no earlier than the finish it scores
    listed["calibration.jsonl"] = [r["hash"] for r in L(cp) if r.get("ts") and eta.pts(r["ts"]) >= t0]
    body = {"type": "NOTE", "note": "UNQUALIFIED-OUTPUT", "since": iso(t0), "until": iso(now), "reason": reason, "config": cfg,
            "claim": "records listed (and status.json/run.log output) in [since, until) were produced by code not matching any qualified manifest",
            "falsifier": "a qualified manifest covering the code that ran in this interval is produced => this note FAILS(1)", "verdict": 0, "listed": listed}
    if os.path.exists(fp): eta.append_chain(fp, dict(body, ledger="forecasts.jsonl"))
    if os.path.exists(sp): eta.append_chain(sp, dict(body, ledger="scores.jsonl"))
    if os.path.exists(cp): learn.append(dict(body, ledger="calibration.jsonl"), cp)
    append(dict(body, ledger="qualification.jsonl"), os.path.join(d, "qualification.jsonl"))
    print("NOTE appended: unqualified since %s: %s" % (iso(t0), {k: len(v) for k, v in listed.items()}))
