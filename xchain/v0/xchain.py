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

def order_consistent(mine, peer_selfheads):
    j = 0
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
        if found < 0:
            if ph in peer_selfheads:
                return False, "out-of-order " + ph[:16]
            return False, "missing " + ph[:16]
        j = found + 1
    return True, "ok"

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
            peer_selfheads = [p.get("self_head") for p in peer]
            mine = []
            for r in recs:
                if "peers" in r and Y in r["peers"]:
                    mine.append(r["peers"][Y])
            ok, msg = order_consistent(mine, peer_selfheads)
            if not ok:
                print("CROSSCHECK FAIL vs %s: %s" % (Y, msg)); sys.exit(1)
            print("CROSSCHECK OK vs %s: %d recorded heads consistent" % (Y, len([m for m in mine if not str(m).startswith('GENESIS:')])))
            checked += 1
        print("CROSSCHECK total peers verified: %d" % checked)
    if getattr(args, "peer_file", None) and os.path.exists(args.peer_file):
        peer = read_chain(args.peer_file)
        peer_selfheads = [p.get("self_head") for p in peer]
        mine = [r["peer_head"] for r in recs if "peer_head" in r]
        ok, msg = order_consistent(mine, peer_selfheads)
        if not ok:
            print("CROSSCHECK FAIL (peer-file): %s" % msg); sys.exit(1)
        print("CROSSCHECK OK (peer-file): %d heads consistent" % len([m for m in mine if str(m) not in ("GENESIS_NO_PEER","BOOTSTRAP","SEED")]))
    print("PASS")

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
    v.set_defaults(func=cmd_verify)
    args = p.parse_args()
    if not getattr(args, "func", None):
        p.print_help(); sys.exit(2)
    args.func(args)

if __name__ == "__main__":
    main()
