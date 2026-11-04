#!/usr/bin/env python3
"""SAT implant verifier. Stdlib only. No network. Read-only.
usage: python3 verify.py [--fast]     (--fast skips files > 1 GB; they print UNKNOWN)
Checks: (1) RECEIPTS.jsonl hash chain, (2) every receipt's file sha256 vs sat_sha and src_sha,
(3) every line of MANIFEST.sha256. Prints HOLDS / FAIL / UNKNOWN per item; exit 0 if integrity HOLDS."""
import sys, os, json, hashlib
D = os.path.dirname(os.path.abspath(__file__)); FAST = "--fast" in sys.argv
NAMES = {0: "HOLDS", 1: "FAIL", 2: "UNKNOWN"}; cache = {}
def sha(rel):
    p = os.path.join(D, rel)
    if rel in cache: return cache[rel]
    if not os.path.isfile(p): return None
    if FAST and os.path.getsize(p) > 1 << 30: return "SKIPPED"
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    cache[rel] = h.hexdigest(); return cache[rel]
bad = 0; unk = 0; claims = {0: 0, 1: 0, 2: 0}
print("== 1. RECEIPTS.jsonl chain")
prev = "0" * 64; n = 0
for raw in open(os.path.join(D, "RECEIPTS.jsonl"), "rb").read().split(b"\n"):
    if not raw: continue
    r = json.loads(raw)
    if r.get("prev") != prev or r.get("n") != n: print(f"FAIL    chain break at n={n}"); bad += 1
    prev = hashlib.sha256(raw).hexdigest(); n += 1
    v = r["verdict"]; claims[v] += 1; st = NAMES[v]
    if r.get("sat_path"):
        got = sha(r["sat_path"])
        if got == "SKIPPED": st = "UNKNOWN"; unk += 1; note = "skipped (--fast)"
        elif got != r["sat_sha"]: st = "FAIL"; bad += 1; note = f"sat_sha now {got}"
        elif r.get("src_sha") and r["src_sha"] != got and v == 0: st = "FAIL"; bad += 1; note = "src_sha != sat_sha"
        else: note = "sha ok"
    else: note = r.get("kind", "note")
    print(f"{st:8}{r['n']:4} {r['id']}  [{note}]" + (f"  reason: {r['reason']}" if v != 0 and r.get("reason") else ""))
print(f"chain: {n} receipts, head {prev}")
head_file = os.path.join(D, "RECEIPTS.head")
if os.path.exists(head_file):
    hf = open(head_file).read().split()[0]
    print(("HOLDS   " if hf == prev else "FAIL    ") + "RECEIPTS.head matches chain head"); bad += hf != prev
print("== 2. MANIFEST.sha256")
m_ok = m_bad = 0
for l in open(os.path.join(D, "MANIFEST.sha256")):
    h, rel = l.rstrip("\n").split("  ", 1); got = sha(rel)
    if got == "SKIPPED": print(f"UNKNOWN {rel} (skipped --fast)"); unk += 1
    elif got == h: m_ok += 1
    else: print(f"FAIL    {rel} got {got}"); m_bad += 1
bad += m_bad
print(f"manifest: {m_ok} HOLDS, {m_bad} FAIL")
print("== summary")
print(f"recorded verdicts: HOLDS={claims[0]} FAIL={claims[1]} UNKNOWN={claims[2]} (see reasons above)")
print("INTEGRITY " + ("FAIL" if bad else ("UNKNOWN (fast mode skipped large files)" if unk else "HOLDS")) + f"  failures={bad}")
sys.exit(1 if bad else (2 if unk else 0))
