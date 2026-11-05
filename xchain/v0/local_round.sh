#!/bin/bash
# Local XCHAIN mesh round on NIKOLAI. Read-only on peers. No TV writes.
# Not scheduled. Kam runs it by hand.
set -u
exec python3 -B - "$@" << 'PY'
import hashlib, json, os, shutil, subprocess, tempfile, time
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
XDIR = os.path.join(HOME, "xchain")
XPY = os.path.join(XDIR, "xchain.py")
BASE = os.path.join(XDIR, "baselines", "BASELINE-atom.json")
BASE_SHA = "321fe6a4fc782021e187afbf919eb39ea29fde1c9ad269c241a78c590185fa4a"
DEVICES = ["NIKOLAI", "ROACH", "SOV", "SOAP", "TV"]
OPTIONAL = ["SOAP"]
ROACH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "roach@<TAILNET-IP>"]
TV_CAT = (
    "timeout 25 adb -s <LAN-IP>:5555 exec-out run-as com.termux "
    "cat /data/data/com.termux/files/home/xchain/xchain.jsonl"
)


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def run(cmd, timeout):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return p.returncode, p.stdout
    except (subprocess.TimeoutExpired, OSError):
        return 124, b""


def run_remote(cmd, timeout):
    last = (124, b"")
    for delay in (0, 1, 2):
        if delay:
            time.sleep(delay)
        last = run(cmd, timeout)
        rc, out = last
        if rc == 0 and out.strip():
            return last
    return last


def pull(name):
    if name == "NIKOLAI":
        path = os.path.join(XDIR, "xchain.jsonl")
        try:
            return open(path, "rb").read(), "local"
        except OSError:
            return None, "local"
    if name == "ROACH":
        rc, out = run_remote(ROACH + ["cat", "/home/roach/xchain/xchain.jsonl"], 25)
        return (out, "ssh") if rc == 0 and out.strip() else (None, "ssh")
    if name == "SOV":
        rc, out = run_remote(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "sov",
             "type", r"C:\Users\<user>\xchain\xchain.jsonl"],
            20,
        )
        return (out, "ssh") if rc == 0 and out.strip() else (None, "ssh")
    if name == "SOAP":
        rc, out = run_remote(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
             "-o", "StrictHostKeyChecking=yes", "kamron@<TAILNET-IP>",
             "cat", "xchain/xchain.jsonl"],
            15,
        )
        return (out, "ssh") if rc == 0 and out.strip() else (None, "ssh")
    if name == "TV":
        rc, out = run_remote(ROACH + [TV_CAT], 40)
        return (out, "roach-adb-read") if rc == 0 and out.strip() else (None, "roach-adb-read")
    return None, "UNKNOWN"


def repeats_and_aba(heads):
    seen = []
    runs = []
    prev = None
    run = 0
    aba = False
    for h in heads:
        if h == prev:
            run += 1
            continue
        if prev is not None and run > 1:
            runs.append(run)
        if h in seen:
            aba = True
        seen.append(h)
        prev = h
        run = 1
    if prev is not None and run > 1:
        runs.append(run)
    return runs, aba


def verify_chain(name, blob, work):
    d = os.path.join(work, name)
    os.makedirs(d)
    open(os.path.join(d, "xchain.jsonl"), "wb").write(blob)
    env = dict(os.environ, XCHAIN_DIR=d, XCHAIN_DEVICE=name, PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([ "python3", "-B", XPY, "verify"], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, env=env, timeout=60)
    text = p.stdout.decode("ascii", "replace")
    return p.returncode == 0 and "CHAIN OK" in text and "\nPASS" in ("\n" + text)


def main():
    utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_bytes = open(BASE, "rb").read()
    base_got = sha_bytes(base_bytes)
    atom = json.loads(base_bytes.decode("utf-8"))
    notes = []
    devices = {}
    fail = base_got != BASE_SHA
    if fail:
        notes.append("baseline sha mismatch")
    work = tempfile.mkdtemp(prefix="xchain-local-round-", dir="/tmp")
    try:
        for name in DEVICES:
            row = {"route": None, "status": "UNREACHABLE", "records": None, "head": None,
                   "repeats": [], "aba": False, "atom": "UNKNOWN"}
            blob, route = pull(name)
            row["route"] = route
            if blob is None:
                if name in OPTIONAL:
                    row["status"] = "SKIP"
                else:
                    row["status"] = "UNREACHABLE"
                    notes.append("HOLD %s offline" % name)
                devices[name] = row
                continue
            try:
                recs = [json.loads(ln) for ln in blob.splitlines() if ln.strip()]
            except (json.JSONDecodeError, UnicodeError):
                row["status"] = "FAIL"
                devices[name] = row
                fail = True
                continue
            row["records"] = len(recs)
            row["head"] = recs[-1].get("hash") if recs else None
            ok = verify_chain(name, blob, work)
            heads = [r.get("self_head") for r in recs]
            runs, aba = repeats_and_aba(heads)
            row["repeats"] = runs
            row["aba"] = aba
            for n in runs:
                notes.append("%s repeat %d" % (name, n))
            if aba:
                notes.append("%s ABA FAIL" % name)
            spec = (atom.get("devices") or {}).get(name) or {}
            atom_head = spec.get("chain_head")
            atom_n = spec.get("records")
            hashes = [r.get("hash") for r in recs]
            if atom_head in hashes and isinstance(atom_n, int) and hashes.index(atom_head) == atom_n - 1 and len(recs) >= atom_n:
                row["atom"] = "EXTENDS"
            else:
                row["atom"] = "BROKEN"
                notes.append("ATOM BROKEN %s" % name)
            if ok and not aba and row["atom"] == "EXTENDS":
                row["status"] = "OK"
            else:
                row["status"] = "FAIL"
                fail = True
            devices[name] = row
    finally:
        shutil.rmtree(work, ignore_errors=True)

    offline = [name for name, row in devices.items() if row["status"] == "UNREACHABLE"]
    if fail:
        result = "FAIL"
    elif offline:
        result = "HOLD"
    else:
        result = "PASS"
    receipt = {
        "baseline_sha256": base_got,
        "baseline_ok": base_got == BASE_SHA,
        "devices": devices,
        "host": "NIKOLAI",
        "notes": notes,
        "optional": list(OPTIONAL),
        "result": result,
        "utc": utc,
    }
    body = (json.dumps(receipt, indent=1, sort_keys=True) + "\n").encode("ascii")
    rdir = os.path.join(XDIR, "rounds")
    os.makedirs(rdir, exist_ok=True)
    rpath = os.path.join(rdir, utc + ".json")
    digest = sha_bytes(body)
    with open(rpath, "xb") as f:
        f.write(body)
    with open(rpath + ".sha256", "x") as f:
        f.write("%s  %s\n" % (digest, os.path.basename(rpath)))

    counts = {"HOLDS": 0, "RECURRED": 0, "UNKNOWN": 0}
    results = []
    for name, row in devices.items():
        if row["status"] == "OK":
            code, verdict = 0, "HOLDS"
        elif row["status"] in ("UNREACHABLE", "SKIP"):
            code, verdict = 2, "UNKNOWN"
        else:
            code, verdict = 1, "RECURRED"
        counts[verdict] = counts.get(verdict, 0) + 1
        results.append({
            "code": code,
            "id": "XCHAIN-" + name,
            "output": "%s records=%s atom=%s" % (row["status"], row["records"], row["atom"]),
            "ran_on": "nikolai",
            "run": "nikolai",
            "secs": 0,
            "verdict": verdict,
        })
    guard = {
        "counts": counts,
        "host": "<user>-ideacentre-510A-15ICB",
        "results": results,
        "round_receipt": rpath,
        "round_sha256": digest,
        "utc": utc,
    }
    gdir = os.path.join(HOME, "fullcircle", "fails", "imports")
    os.makedirs(gdir, exist_ok=True)
    gpath = os.path.join(gdir, "xchain-round-%s.json" % utc)
    gbody = (json.dumps(guard, indent=1, sort_keys=True) + "\n").encode("ascii")
    with open(gpath, "xb") as f:
        f.write(gbody)

    for line in notes:
        print(line)
    parts = []
    for name in DEVICES:
        row = devices[name]
        if row["status"] in ("UNREACHABLE", "SKIP"):
            parts.append("%s=%s" % (name, row["status"]))
        else:
            parts.append("%s=%s %s" % (name, row["records"], row["status"]))
    print(result + " " + " ".join(parts))


if __name__ == "__main__":
    main()
PY
