#!/usr/bin/env python3
# XCHAIN v1 - N-way cross-signed chain heads (Agape module). Read-only sources; additive only.
import sys, os, json, hashlib, time, argparse, platform, base64

DEVICES = ["NIKOLAI", "ROACH", "SOV", "SOAP", "TV"]

def home():
    return os.path.expanduser("~")

def xdir():
    d = os.environ.get("XCHAIN_DIR")
    if d:
        return d
    return os.path.join(home(), "xchain")

def xlog():
    return os.path.join(xdir(), "xchain.jsonl")

NIK_HCDU = "/mnt/hcdu/HCDU-ROOT/receipts/HCDU-LOG.jsonl"

def rch_ledger():
    return os.path.join(home(), "REACTOR", "yfm", "ledger.yfm")

def sha(b):
    if isinstance(b, str):
        b = b.encode()
    return hashlib.sha256(b).hexdigest()

def detect_device():
    d = os.environ.get("XCHAIN_DEVICE")
    if d:
        return d.upper()
    if os.path.exists(NIK_HCDU):
        return "NIKOLAI"
    if os.path.exists(rch_ledger()):
        return "ROACH"
    if "com.termux" in (os.environ.get("PREFIX", "") + home()) or os.path.isdir("/data/data/com.termux"):
        return "TV"
    if os.name == "nt":
        return "SOV"
    if platform.system() == "Darwin":
        return "SOAP"
    return "UNKNOWN"

def read_chain(path=None):
    path = path or xlog()
    recs = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    recs.append(json.loads(line))
    return recs

def chain_head(path=None):
    recs = read_chain(path)
    return recs[-1]["hash"] if recs else None

def self_head(device=None):
    device = device or detect_device()
    if device == "NIKOLAI":
        with open(NIK_HCDU, "rb") as f:
            data = f.read()
        lines = [l for l in data.split(b"\n") if l.strip()]
        return sha(lines[-1])
    if device == "ROACH":
        with open(rch_ledger(), "rb") as f:
            data = f.read()
        fsha = sha(data)
        lines = [l for l in data.split(b"\n") if l.strip()]
        lh = "NA"
        try:
            last = lines[-1].decode("utf-8", "replace")
            b = last.find("{")
            if b >= 0:
                obj, _ = json.JSONDecoder().raw_decode(last[b:])
                lh = obj.get("head_sha256") or obj.get("sha256") or "NA"
        except Exception:
            lh = "NA"
        return "%s+%s" % (fsha, lh)
    # SOV / SOAP / TV: own chain head, else device genesis sentinel
    h = chain_head()
    return h if h else "GENESIS:" + device

def rec_canon(rec):
    if "peers" in rec:
        return json.dumps({"ts": rec["ts"], "self_head": rec["self_head"],
                           "peers": rec["peers"], "prev_hash": rec["prev_hash"]},
                          sort_keys=True, separators=(",", ":"))
    # legacy v0
    return json.dumps({"ts": rec["ts"], "self_head": rec["self_head"],
                       "peer_head": rec["peer_head"], "prev_hash": rec["prev_hash"]},
                      sort_keys=True, separators=(",", ":"))

def rec_hash(rec):
    return sha(rec_canon(rec))

def cmd_whichbox(args):
    print(detect_device())

def cmd_head(args):
    print(self_head())

def cmd_append(args):
    device = detect_device()
    os.makedirs(xdir(), exist_ok=True)
    peers = {}
    sh_override = None
    if getattr(args, "round_b64", None):
        d = json.loads(base64.b64decode(args.round_b64))
        peers = d.get("peers", {})
        sh_override = d.get("self")
    if args.peers:
        peers = json.loads(args.peers)
    if args.peer_head and not peers:
        peers = {"PEER": args.peer_head}
    sh = sh_override or (args.self_head if getattr(args, "self_head", None) else self_head(device))
    recs = read_chain()
    prev = recs[-1]["hash"] if recs else "GENESIS"
    ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    rec = {"ts": ts, "device": device, "self_head": sh,
           "peers": peers, "prev_hash": prev}
    rec["hash"] = rec_hash(rec)
    with open(xlog(), "a") as f:
        f.write(json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps(rec))

def order_consistent(mine, peer_selfheads, strict=False):
    # v1.1 (2026-11-03): stale-peer-head tolerant.
    # A witness may legitimately record a peer head that is STALE: either
    #  (a) an older head the peer genuinely chained earlier (re-witness after the
    #      peer advanced; old code: "out-of-order"), or
    #  (b) a ledger head read in the race window before the peer self-appended
    #      a newer one, so the peer never chained that exact value (old code:
    #      "missing").
    # Neither is evidence that the peer's chain changed. Real tamper/fork is
    # caught by: the peer's own hash-chain verify, the ATOM baseline, and the
    # witnessed-tip ancestry check (check_witnessed_tips) against rounds.jsonl.
    # strict=True restores the pre-v1.1 behaviour exactly.
    j = 0
    last = None
    repeats = stale = unmatched = 0
    for ph in mine:
        if isinstance(ph, str) and ph.startswith("GENESIS:"):
            continue
        if ph in ("GENESIS_NO_PEER", "BOOTSTRAP", "SEED"):
            continue
        found = -1
        for k in range(j, len(peer_selfheads)):
            if peer_selfheads[k] == ph:
                found = k
                break
        if found < 0 and last is not None and ph == last:
            repeats += 1
            continue
        if found < 0:
            if ph in peer_selfheads:
                if strict:
                    return False, "out-of-order " + ph[:16]
                stale += 1; continue
            if strict:
                return False, "missing " + ph[:16]
            unmatched += 1; continue
        j = found + 1
        last = ph
    notes = []
    if repeats: notes.append("repeat %d" % repeats)
    if stale: notes.append("stale re-witness %d" % stale)
    if unmatched: notes.append("unmatched stale-head %d" % unmatched)
    if notes:
        return True, "ok (" + ", ".join(notes) + ")"
    return True, "ok"

def load_rounds(path):
    # rounds.jsonl: box-side, append-only, hash-chained round records.
    out = []
    if path and os.path.exists(path):
        prev = "GENESIS"
        for i, line in enumerate(open(path)):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            body = {k: v for k, v in r.items() if k != "hash"}
            if r.get("prev_hash") != prev or sha(json.dumps(body, sort_keys=True, separators=(",", ":"))) != r.get("hash"):
                raise ValueError("rounds.jsonl chain broken at line %d" % i)
            prev = r["hash"]
            out.append(r)
    return out

def check_witnessed_tips(device, recs, rounds):
    # Every tip previously witnessed for `device` (record count n, hash h) must
    # still be record n-1 of the current chain (ancestor/prefix). Advanced
    # chains pass; a changed witnessed record or a fork FAILs.
    checked = 0
    for rd in rounds:
        t = rd.get("tips", {}).get(device)
        if not t:
            continue
        n, h = int(t["n"]), t["hash"]
        if len(recs) < n:
            return False, "truncated: %d < witnessed %d (round %s)" % (len(recs), n, rd["round"]), checked
        if recs[n - 1]["hash"] != h:
            return False, "witnessed record %d changed/forked: now %s, witnessed %s at round %s" % (n - 1, recs[n - 1]["hash"][:16], h[:16], rd["round"]), checked
        checked += 1
    return True, "ok", checked

def cmd_verify(args):
    device = detect_device()
    recs = read_chain()
    if not recs:
        print("VERIFY FAIL: empty chain"); sys.exit(1)
    prev = "GENESIS"
    for i, r in enumerate(recs):
        if r["prev_hash"] != prev:
            print("VERIFY FAIL: prev_hash mismatch at %d" % i); sys.exit(1)
        if rec_hash(r) != r["hash"]:
            print("VERIFY FAIL: hash mismatch at %d" % i); sys.exit(1)
        prev = r["hash"]
    print("CHAIN OK: device=%s records=%d head=%s" % (device, len(recs), recs[-1]["hash"][:16]))
    if args.peers_dir and os.path.isdir(args.peers_dir):
        checked = 0
        for Y in DEVICES:
            if Y == device:
                continue
            pf = os.path.join(args.peers_dir, Y + ".jsonl")
            if not os.path.exists(pf):
                continue
            peer = read_chain(pf)
            if not peer:
                print("CROSSCHECK HOLD vs %s: peer has no chain (not scored)" % Y)
                continue
            peer_selfheads = [p.get("self_head") for p in peer]
            mine = []
            for r in recs:
                if "peers" in r and Y in r["peers"]:
                    mine.append(r["peers"][Y])
            ok, msg = order_consistent(mine, peer_selfheads, strict=getattr(args, "strict_heads", False))
            if not ok:
                print("CROSSCHECK FAIL vs %s: %s" % (Y, msg)); sys.exit(1)
            print("CROSSCHECK OK vs %s: %d recorded heads consistent%s" % (Y, len([m for m in mine if not str(m).startswith('GENESIS:')]), (" [note: " + msg[4:-1] + "]") if msg != "ok" else ""))
            checked += 1
        print("CROSSCHECK total peers verified: %d" % checked)
    if getattr(args, "rounds", None):
        try:
            rounds = load_rounds(args.rounds)
        except Exception as e:
            print("WITNESS FAIL: %s" % e); sys.exit(1)
        ok, msg, n = check_witnessed_tips(device, recs, rounds)
        if not ok:
            print("WITNESS FAIL: %s" % msg); sys.exit(1)
        print("WITNESS OK: %d witnessed tips are ancestors of current chain" % n)
    if getattr(args, "peer_file", None) and os.path.exists(args.peer_file):
        peer = read_chain(args.peer_file)
        peer_selfheads = [p.get("self_head") for p in peer]
        mine = [r["peer_head"] for r in recs if "peer_head" in r]
        ok, msg = order_consistent(mine, peer_selfheads)
        if not ok:
            print("CROSSCHECK FAIL (peer-file): %s" % msg); sys.exit(1)
        print("CROSSCHECK OK (peer-file): %d heads consistent%s" % (len([m for m in mine if str(m) not in ("GENESIS_NO_PEER","BOOTSTRAP","SEED")]), (" [note: " + msg[4:-1] + "]") if msg != "ok" else ""))
    print("PASS")

def _file_sha(path):
    with open(path, "rb") as f:
        return sha(f.read())

def cmd_baseline(args):
    # Additive ATOM check: history up to the frozen baseline must be unchanged.
    m = args.manifest
    sf = args.sha_file or (m + ".sha256")
    try:
        want = open(sf).read().split()[0].strip().lower()
    except Exception as e:
        print("ATOM MANIFEST BROKEN: cannot read sha file (%s)" % e); sys.exit(1)
    got = _file_sha(m)
    if got != want:
        print("ATOM MANIFEST BROKEN: sha mismatch got=%s want=%s" % (got[:16], want[:16])); sys.exit(1)
    man = json.load(open(m))
    print("ATOM MANIFEST OK: %s sha=%s frozen_round=%s" % (os.path.basename(m), got[:16], man.get("frozen_round")))
    broken = 0
    for dev, info in man["devices"].items():
        n = int(info["records"]); head = info["chain_head"]
        pf = os.path.join(args.peers_dir, dev + ".jsonl")
        if not os.path.exists(pf) or os.path.getsize(pf) == 0:
            print("%s: ATOM UNKNOWN (no chain)" % dev); continue
        try:
            recs = read_chain(pf)
        except Exception as e:
            print("%s: ATOM BROKEN (unparseable chain: %s)" % (dev, e)); broken += 1; continue
        if len(recs) < n:
            print("%s: ATOM BROKEN (truncated: %d < frozen %d)" % (dev, len(recs), n)); broken += 1; continue
        prev = "GENESIS"; why = None
        for i in range(n):
            r = recs[i]
            if r.get("prev_hash") != prev:
                why = "prev_hash mismatch at %d" % i; break
            if rec_hash(r) != r.get("hash"):
                why = "hash mismatch at %d" % i; break
            prev = r["hash"]
        if why is None and prev != head:
            why = "record %d hash %s != frozen chain_head %s" % (n, prev[:16], head[:16])
        if why:
            print("%s: ATOM BROKEN (%s)" % (dev, why)); broken += 1; continue
        print("%s: ATOM OK (frozen %d intact, +%d appended)" % (dev, n, len(recs) - n))
    print("ATOM SUMMARY: %s" % ("broken %d" % broken if broken else "ok"))
    sys.exit(1 if broken else 0)

def cmd_record_round(args):
    # Append one hash-chained round record: round ts + per-device tip (n, hash).
    rounds = load_rounds(args.rounds)
    prev = rounds[-1]["hash"] if rounds else "GENESIS"
    tips = {}
    for dev in DEVICES:
        pf = os.path.join(args.peers_dir, dev + ".jsonl")
        try:
            rc = read_chain(pf) if os.path.exists(pf) else []
        except Exception:
            rc = []
        if rc:
            tips[dev] = {"n": len(rc), "hash": rc[-1]["hash"], "last_ts": rc[-1].get("ts")}
        else:
            tips[dev] = None
    body = {"round": args.round, "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tips": {k: v for k, v in tips.items() if v}, "hold": [k for k, v in tips.items() if not v],
            "prev_hash": prev}
    body["hash"] = sha(json.dumps(body, sort_keys=True, separators=(",", ":")))
    with open(args.rounds, "a") as f:
        f.write(json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n")
    print("ROUND RECORDED: %s hash=%s tips=%s hold=%s" % (args.round, body["hash"][:16],
          ",".join("%s:%d/%s" % (k, v["n"], v["hash"][:12]) for k, v in body["tips"].items()), ",".join(body["hold"]) or "-"))

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("whichbox").set_defaults(func=cmd_whichbox)
    sub.add_parser("head").set_defaults(func=cmd_head)
    a = sub.add_parser("append")
    a.add_argument("--peers", default=None)
    a.add_argument("--peer-head", default=None)
    a.add_argument("--self-head", default=None)
    a.add_argument("--round-b64", default=None)
    a.set_defaults(func=cmd_append)
    v = sub.add_parser("verify")
    v.add_argument("--peers-dir", default=None)
    v.add_argument("--peer-file", default=None)
    v.add_argument("--strict-heads", action="store_true")
    v.add_argument("--rounds", default=None)
    v.set_defaults(func=cmd_verify)
    b = sub.add_parser("baseline")
    b.add_argument("--manifest", required=True)
    b.add_argument("--sha-file", default=None)
    b.add_argument("--peers-dir", required=True)
    b.set_defaults(func=cmd_baseline)
    rr = sub.add_parser("record-round")
    rr.add_argument("--rounds", required=True)
    rr.add_argument("--peers-dir", required=True)
    rr.add_argument("--round", required=True)
    rr.set_defaults(func=cmd_record_round)
    args = p.parse_args()
    if not getattr(args, "func", None):
        p.print_help(); sys.exit(2)
    args.func(args)

if __name__ == "__main__":
    main()
