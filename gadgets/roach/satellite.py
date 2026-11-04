#!/usr/bin/env python3
"""XCHAIN witness satellite. Pulls NIKOLAI's coord ledger + peer chains READ-ONLY over signed FC-Link,
verifies independently, cross-checks the other satellite, appends ONLY to its own hash-chained verdicts.jsonl.
Flags: DISAGREE, ATOM_BREAK, STALE (>75 min), LEDGER_BREAK, FAIL:<dev>, NO_SOURCE. TV/SAT are HOLD, never FAIL."""
import os, sys, json, hashlib, tempfile, shutil, subprocess, argparse
from datetime import datetime, timezone, timedelta
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import fcl
XPY = os.path.join(H, "xchain_v11.py"); BASE = os.path.join(H, "BASELINE-atom.json"); PIN = "321fe6a4"
VER = os.path.join(H, "verdicts.jsonl"); CONF = json.load(open(os.path.join(H, "satellite.conf.json")))
REQ = ["NIKOLAI", "ROACH", "SOV", "SOAP"]; INT = ["TV", "SAT"]; STALE_MIN = 75
def sha(b): return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()
def canon(o): return json.dumps(o, sort_keys=True, separators=(",", ":"))
def now(): return datetime.now(timezone.utc)

def pull(work):
    last = None
    for n in CONF["sources"]:
        try:
            c = _cli(n)
            c.get("xchain-coord-rounds.jsonl", os.path.join(work, "rounds.jsonl"))
            pd = os.path.join(work, "peers"); os.makedirs(pd, exist_ok=True); got = {}
            for d in REQ + INT:
                try: got[d] = c.get("xchain-coord-peer-%s.jsonl" % d, os.path.join(pd, d + ".jsonl"))["sha256"]
                except Exception: pass
            return n["host"], pd, got
        except Exception as e: last = "%s: %s" % (n["host"], e)
    raise RuntimeError(last)

def ledger_check(path):
    rows = [json.loads(l) for l in open(path) if l.strip()]; prev = None
    for i, r in enumerate(rows):
        b = dict(r); h = b.pop("hash")
        if sha(canon(b)) != h: return False, rows, "row %d hash mismatch" % i
        if prev is not None and r["prev_hash"] != prev: return False, rows, "row %d prev_hash break" % i
        prev = h
    return True, rows, "%d rows linked" % len(rows)

def xv(args, env=None, t=180):
    p = subprocess.run([sys.executable, "-B", XPY] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       env=dict(os.environ, **(env or {})), timeout=t)
    return p.returncode, p.stdout.decode(errors="replace")

def verify_dev(d, chain, pd, rounds, work):
    t = tempfile.mkdtemp(dir=work); shutil.copy(chain, os.path.join(t, "xchain.jsonl"))
    rc, out = xv(["verify", "--peers-dir", pd, "--rounds", rounds], {"XCHAIN_DEVICE": d, "XCHAIN_DIR": t})
    return rc, out

def evaluate(pd, rounds, work, chains=None):
    flags = []; dev = {}
    ok, rows, why = ledger_check(rounds)
    if not ok: flags.append("LEDGER_BREAK")
    tip = rows[-1] if rows else {}
    for d in REQ + INT:
        f = (chains or {}).get(d) or os.path.join(pd, d + ".jsonl")
        if not os.path.exists(f) or os.path.getsize(f) == 0:
            dev[d] = "HOLD (no chain)" if d in INT else "FAIL (no chain)"
            if d in REQ: flags.append("FAIL:" + d)
            continue
        rc, out = verify_dev(d, f, pd, rounds, work)
        if rc == 0: dev[d] = "PASS"
        elif d in INT: dev[d] = "HOLD (verify rc %d)" % rc
        else:
            dev[d] = "FAIL " + " | ".join(l for l in out.splitlines() if "FAIL" in l or "changed" in l or "fork" in l)[:300]
            flags.append("FAIL:" + d)
    if not (open(BASE, "rb").read() and sha(open(BASE, "rb").read()).startswith(PIN)): flags.append("ATOM_BREAK"); atom = "manifest pin mismatch"
    else:
        rc, out = xv(["baseline", "--manifest", BASE, "--peers-dir", pd])
        atom = next((l.split("ATOM SUMMARY: ")[1] for l in out.splitlines() if "ATOM SUMMARY: " in l), "broken")
        if rc != 0 or atom != "ok": flags.append("ATOM_BREAK")
    if tip:
        age = now() - datetime.strptime(tip["recorded_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if age > timedelta(minutes=STALE_MIN): flags.append("STALE")
    return flags, dev, atom, why, rows, tip

def _cli(n): return fcl.FCLink(n["host"], n.get("port", 8765), n.get("keyfile", "~/.config/fclink/key"), 20)
def other_last(rows):
    # other satellite's newest verdict, published as xchain-satv-<NAME>-<utc>-<h>.json in NIKOLAI's FC-Link inbox
    o = CONF["other"]; last = None
    for n in CONF["sources"]:
        try:
            c = _cli(n); pre = "xchain-satv-%s-" % o["name"]
            names = sorted(f["name"] for f in c.ls() if f["name"].startswith(pre) and f["name"].endswith(".json"))
            if not names: return {"status": "EMPTY"}, False
            tmp = tempfile.mktemp(dir=H, prefix=".other-"); c.get(names[-1], tmp)
            l = json.load(open(tmp)); os.remove(tmp)
            b = dict(l); h = b.pop("hash")
            if sha(canon(b)) != h: return {"status": "BAD_HASH", "file": names[-1]}, True
            hashes = {r["hash"] for r in rows}; dis = l["ledger_tip"]["hash"] not in hashes and l["ledger_tip"]["hash"] is not None
            if l["verdict"] == "OK" and not dis:
                pass
            return {"status": "OK", "file": names[-1], "sat": l["sat"], "ts": l["ts"], "hash": h, "verdict": l["verdict"],
                    "flags": l.get("flags"), "ledger_tip": l["ledger_tip"], "tip_in_my_ledger": not dis}, dis
        except Exception as e: last = str(e)[:160]
    return {"status": "UNAVAILABLE", "why": last}, False

def append(body):
    vs = [json.loads(l) for l in open(VER) if l.strip()] if os.path.exists(VER) else []
    body["prev_hash"] = vs[-1]["hash"] if vs else "GENESIS"; body["hash"] = sha(canon(body))
    with open(VER, "a") as f: f.write(canon(body) + "\n")
    return body["hash"]

def publish(body):
    name = "xchain-satv-%s-%s-%s.json" % (CONF["name"], body["ts"].replace("-", "").replace(":", ""), body["hash"][:8])
    tmp = os.path.join(H, "." + name); open(tmp, "w").write(canon(body) + "\n")
    for n in CONF["sources"]:
        try: _cli(n).put(tmp, name); print("published", name, "via", n["host"]); break
        except Exception as e: print("publish via", n["host"], "failed:", str(e)[:120])
    os.remove(tmp)

def last_v(): return [json.loads(l) for l in open(VER) if l.strip()][-1]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tamper", metavar="DEV"); a = ap.parse_args()
    try: os.nice(10)
    except Exception: pass
    work = tempfile.mkdtemp(prefix="sat-", dir=H); ts = now().strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        try: src, pd, got = pull(work)
        except Exception as e:
            if a.tamper: print("no source", e); return 2
            h = append({"sat": CONF["name"], "ts": ts, "verdict": "ALERT", "flags": ["NO_SOURCE"], "why": str(e)[:200],
                        "ledger_tip": {"round": None, "hash": None}}); publish(last_v()); print("VERDICT ALERT NO_SOURCE", h); return 1
        rounds = os.path.join(work, "rounds.jsonl")
        if a.tamper:
            import importlib.util as iu
            spec = iu.spec_from_file_location("xv", XPY); m = iu.module_from_spec(spec); spec.loader.exec_module(m)
            d = a.tamper; rows = [json.loads(l) for l in open(rounds) if l.strip()]; n = rows[-1]["tips"][d]["n"]
            src_f = os.path.join(pd, d + ".jsonl"); lines = open(src_f).read().splitlines()
            r = json.loads(lines[n - 1]); r["self_head"] = "TAMPERED-" + str(r["self_head"])[:8]; r["hash"] = m.rec_hash(r)
            lines[n - 1] = json.dumps(r, sort_keys=True); prev = r["hash"]
            for i in range(n, len(lines)):
                q = json.loads(lines[i]); q["prev_hash"] = prev; q["hash"] = m.rec_hash(q); prev = q["hash"]; lines[i] = json.dumps(q, sort_keys=True)
            tf = os.path.join(work, d + ".tampered.jsonl"); open(tf, "w").write("\n".join(lines) + "\n")
            flags, dev, atom, why, _, tip = evaluate(pd, rounds, work, chains={d: tf})
            res = {"test": "tamper-detect", "sat": CONF["name"], "ts": ts, "device": d, "altered_record_index": n - 1,
                   "source": src, "source_sha256": got.get(d), "flags": flags, "device_status": dev[d],
                   "expected": "FAIL:" + d, "result": "PASS" if ("FAIL:" + d) in flags else "FAIL",
                   "note": "copy only; verdicts.jsonl NOT appended"}
            os.makedirs(os.path.join(H, "tests"), exist_ok=True)
            p = os.path.join(H, "tests", "tamper-detect-%s.json" % ts.replace(":", "").replace("-", ""))
            b = json.dumps(res, sort_keys=True, indent=1).encode(); open(p, "wb").write(b)
            print("TAMPER", res["result"], flags, "receipt", p, sha(b)); return 0 if res["result"] == "PASS" else 1
        flags, dev, atom, why, rows, tip = evaluate(pd, rounds, work)
        oth, dis = other_last(rows)
        if dis: flags.append("DISAGREE")
        body = {"sat": CONF["name"], "ts": ts, "source": src, "pulled_sha256": got,
                "ledger": {"rows": len(rows), "check": why}, "ledger_tip": {"round": tip.get("round"), "hash": tip.get("hash"),
                "recorded_at": tip.get("recorded_at"), "tips": tip.get("tips"), "hold": tip.get("hold")},
                "devices": dev, "atom": atom, "atom_pin": PIN, "other": oth, "flags": flags,
                "verdict": "OK" if not flags else "ALERT"}
        h = append(body); publish(body)
        print("VERDICT", body["verdict"], flags, "tip", tip.get("round"), str(tip.get("hash"))[:16], "verdict_hash", h)
        return 0 if not flags else 1
    finally: shutil.rmtree(work, ignore_errors=True)

if __name__ == "__main__": sys.exit(main())
