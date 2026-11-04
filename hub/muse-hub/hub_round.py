#!/usr/bin/env python3
"""MUSE HUB — round runner (v1, 2026-11-01, DESK-1 build at founder's word).

The witness hub's heartbeat, coded onto the gadgets themselves: every
ROUND_S seconds this runner (resident on Nikolai) collects fresh
self-heads from the three muse gadgets, stamps one XCHAIN round across
them (Nikolai local, Roach via ssh, hazels-tv via Roach's adb run-as
lane), verifies each stamped chain on its own box, and logs one line.
No desk timer, no desk pings: the cadence lives in this code. The pi-2
puck on SAT witnesses the movement independently.

Peer rules (the fleet's own precedents):
- A device that does not answer is OMITTED from the round's peer sets
  (partial rounds are honest rounds; Oct 28-30 precedent).
- SOV rides as a read peer at its last-witnessed chain head, adopted
  from the newest gadget record that cites it. SOV stamps itself only
  through its own seats (its chain lives outside the hub's lanes).
- One round at a time (flock). A failed round logs and the loop lives.

PATCH v1.1 (2026-11-01, founder's word): core members are NIKOLAI +
ROACH. hazels-tv is an OPTIONAL member: stamped whenever it answers,
omitted without failing the round when it does not. The founder turns
his TV off; SAT stands the persistent pi-2 witness post, so a dark TV
is a normal state of the fleet, never a fault. A member that stamps
but fails verify still fails the round: absence is fine, bad
evidence is not.
"""
import base64
import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
HUB = HOME / "muse-hub"
LOG = HUB / "rounds.log"
STATE = HUB / "state.json"
LATEST = HUB / "latest.json"
XCHAIN = HOME / "xchain" / "xchain.py"
ROUND_S = 600

ROACH_SSH = ["ssh", "-i", str(HOME / ".ssh" / "sat_hemisphere"),
             "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
             "-o", "ConnectTimeout=8", "roach@<TAILNET-IP>"]
TV_TAIL = ("timeout 25 adb -s <TAILNET-IP>:5555 exec-out run-as com.termux "
           "tail -1 /data/data/com.termux/files/home/xchain/xchain.jsonl")
TV_ENV = ("/data/data/com.termux/files/usr/bin/env "
          "XCHAIN_DIR=/data/data/com.termux/files/home/xchain XCHAIN_DEVICE=TV "
          "/data/data/com.termux/files/usr/bin/python3 "
          "/data/data/com.termux/files/home/xchain/xchain.py")
TV_APPEND = "timeout 25 adb -s <TAILNET-IP>:5555 shell run-as com.termux " + TV_ENV + " append --round-b64 "
TV_VERIFY = "timeout 25 adb -s <TAILNET-IP>:5555 shell run-as com.termux " + TV_ENV + " verify"


def now_iso():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def run(cmd, timeout=40):
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.decode(errors="replace")
    except Exception as e:  # noqa: BLE001
        return 124, f"{type(e).__name__}: {e}"


def log_line(text):
    with open(LOG, "a") as f:
        f.write(text + "\n")


def load_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def b64_round(peers):
    return base64.b64encode(json.dumps({"peers": peers}).encode()).decode()


def collect_heads(st):
    heads = {}
    rc, out = run(["python3", str(XCHAIN), "head"], 20)
    if rc == 0 and out.strip():
        heads["NIKOLAI"] = out.strip()
    rc, out = run(ROACH_SSH + ["python3", "~/xchain/xchain.py", "head"], 25)
    if rc == 0 and out.strip():
        heads["ROACH"] = out.strip()
    rc, out = run(ROACH_SSH + [TV_TAIL], 45)
    if rc == 0 and out.strip():
        try:
            heads["TV"] = json.loads(out.strip().splitlines()[-1])["hash"]
        except Exception:  # noqa: BLE001
            pass
    # SOV: last-witnessed value rides in state; refresh from any chain
    # tail that cites a SOV head (tails read during verify last round).
    if st.get("sov_head"):
        heads["SOV"] = st["sov_head"]
    return heads


def peers_for(device, heads):
    return {k: v for k, v in heads.items() if k != device}


def stamp(device, heads):
    peers = peers_for(device, heads)
    if device == "NIKOLAI":
        rc, out = run(["python3", str(XCHAIN), "append", "--round-b64", b64_round(peers)], 20)
    elif device == "ROACH":
        rc, out = run(ROACH_SSH + ["python3", "~/xchain/xchain.py", "append",
                                   "--round-b64", b64_round(peers)], 25)
    elif device == "TV":
        rc, out = run(ROACH_SSH + [TV_APPEND + b64_round(peers)], 45)
    else:
        return None
    if rc != 0 or not out.strip():
        return None
    try:
        return json.loads(out.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return None


def verify(device):
    if device == "NIKOLAI":
        rc, out = run(["python3", str(XCHAIN), "verify"], 60)
    elif device == "ROACH":
        rc, out = run(ROACH_SSH + ["python3", "~/xchain/xchain.py", "verify"], 60)
    elif device == "TV":
        rc, out = run(ROACH_SSH + [TV_VERIFY], 45)
    else:
        return False
    return rc == 0 and "CHAIN OK" in out and "PASS" in out


def refresh_sov_witness(st):
    # Adopt the SOV head cited by the newest record among local + Roach
    # chain tails (the TV's citations arrive via its own tail on Roach
    # reads during collect; here we check the two file-local tails).
    best_ts, best = st.get("sov_head_ts", ""), st.get("sov_head")
    for path in (HOME / "xchain" / "xchain.jsonl",):
        try:
            rec = json.loads(path.read_bytes().splitlines()[-1])
            sov = (rec.get("peers") or {}).get("SOV")
            if sov and rec.get("ts", "") >= best_ts:
                best_ts, best = rec["ts"], sov
        except Exception:  # noqa: BLE001
            pass
    rc, out = run(ROACH_SSH + ["tail", "-1", "~/xchain/xchain.jsonl"], 25)
    if rc == 0 and out.strip():
        try:
            rec = json.loads(out.strip().splitlines()[-1])
            sov = (rec.get("peers") or {}).get("SOV")
            if sov and rec.get("ts", "") >= best_ts:
                best_ts, best = rec["ts"], sov
        except Exception:  # noqa: BLE001
            pass
    rc, out = run(ROACH_SSH + [TV_TAIL], 45)
    if rc == 0 and out.strip():
        try:
            rec = json.loads(out.strip().splitlines()[-1])
            sov = (rec.get("peers") or {}).get("SOV")
            if sov and rec.get("ts", "") >= best_ts:
                best_ts, best = rec["ts"], sov
        except Exception:  # noqa: BLE001
            pass
    st["sov_head"], st["sov_head_ts"] = best, best_ts
    return st


def one_round():
    st = load_state()
    st = refresh_sov_witness(st)
    heads = collect_heads(st)
    gadgets = [d for d in ("NIKOLAI", "ROACH", "TV") if d in heads]
    result = {"ts": now_iso(), "participants": gadgets, "stamps": {}, "verify": {}}
    for d in gadgets:
        rec = stamp(d, heads)
        if rec:
            result["stamps"][d] = rec["hash"]
    for d in result["stamps"]:
        result["verify"][d] = verify(d)
    core = {"NIKOLAI", "ROACH"}
    ok = core.issubset(result["stamps"]) and all(result["verify"].values())
    result["result"] = "PASS" if ok else "PARTIAL"
    result["optional"] = {"TV": "present" if "TV" in gadgets else "absent"}
    LATEST.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    parts = " ".join(f"{d}={result['stamps'][d][:12]}" for d in result["stamps"])
    absent = [d for d in ("NIKOLAI", "ROACH", "TV") if d not in gadgets]
    log_line(f"{result['ts']} round {result['result']} stamps[{parts}] "
             f"verify={result['verify']} absent={absent}")
    st["last_round"] = result["ts"]
    STATE.write_text(json.dumps(st, indent=1, sort_keys=True) + "\n")
    return result


def main():
    HUB.mkdir(exist_ok=True)
    lock = open("/tmp/muse-hub-round.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another hub runner holds the lock; exiting")
        return
    if "--once" in sys.argv:
        print(json.dumps(one_round(), indent=1, sort_keys=True))
        return
    log_line(f"{now_iso()} muse-hub round runner started (cadence {ROUND_S}s)")
    while True:
        try:
            one_round()
        except Exception as e:  # noqa: BLE001 — the heartbeat does not die on a bad round
            log_line(f"{now_iso()} round ERROR {type(e).__name__}: {e}")
        time.sleep(ROUND_S)


if __name__ == "__main__":
    main()
