#!/usr/bin/env python3
"""MUSE DIRECTORY — CHAINER (v1, 2026-11-01, DESK-1).
DESIGN.md S4.3: the chainer READS rounds; it never writes a member's
ledger. This reader polls the witness-hub members' chain tails over
the fleet's read lanes (Nikolai local; Roach via pinned ssh; hazels-tv
via Roach's adb run-as read), and maintains the chain record the
registry and deck render: members, current heads, last COMPLETE round
(every member beating under one stamp window, cross-cited peers),
and evidence-labeled liveness. Its only write is its own output:
~/muse-hub/chain-state.json (plus a copy inside the hub dir for the
registrar's ferry). Read-only on every member, always.

PATCH v1.1 (2026-11-01, founder's word): completeness is computed
over the CORE members (Nikolai + Roach) only. hazels-tv is reported
with its own liveness but never gates the chain status: the founder
turns his TV off, and SAT stands the persistent pi-2 witness post,
so a dark TV is a normal state, not a degradation.
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
OUT = HOME / "muse-hub" / "chain-state.json"
CADENCE_S = 120
STALE_S = 1500  # >2 round cadences without a stamp -> STALE
WINDOW_S = 900  # one stamp window for completeness

ROACH_SSH = ["ssh", "-i", str(HOME / ".ssh" / "sat_hemisphere"),
             "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
             "-o", "ConnectTimeout=8", "roach@<TAILNET-IP>"]
TV_TAIL = ("timeout 25 adb -s <TAILNET-IP>:5555 exec-out run-as com.termux "
           "tail -3 /data/data/com.termux/files/home/xchain/xchain.jsonl")
MEMBERS = ["NIKOLAI", "ROACH", "TV"]
CORE = ["NIKOLAI", "ROACH"]  # v1.1: TV is optional and never gates
IDS = {"NIKOLAI": "nikolai", "ROACH": "roach", "TV": "hazels-tv"}


def run(cmd, timeout=45):
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.decode(errors="replace")
    except Exception:  # noqa: BLE001
        return 124, ""


def tail_records(device):
    if device == "NIKOLAI":
        try:
            lines = (HOME / "xchain" / "xchain.jsonl").read_bytes().splitlines()
            return [json.loads(l) for l in lines[-3:] if l.strip()], len(lines)
        except Exception:  # noqa: BLE001
            return [], None
    if device == "ROACH":
        rc, cnt = run(ROACH_SSH + ["wc", "-l", "<", "~/xchain/xchain.jsonl"], 25)
        rc2, out = run(ROACH_SSH + ["tail", "-3", "~/xchain/xchain.jsonl"], 25)
        n = int(cnt.strip()) if rc == 0 and cnt.strip().isdigit() else None
        if rc2 != 0 or not out.strip():
            return [], n
        return [json.loads(l) for l in out.strip().splitlines() if l.strip()], n
    if device == "TV":
        rc, out = run(ROACH_SSH + [TV_TAIL], 50)
        if rc != 0 or not out.strip():
            return [], None
        recs = [json.loads(l) for l in out.strip().splitlines() if l.strip()]
        return recs, None
    return [], None


def parse_ts(s):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except Exception:  # noqa: BLE001
        return None


def one_pass():
    now = time.time()
    members = {}
    lasts = {}
    for d in MEMBERS:
        recs, n = tail_records(d)
        if not recs:
            members[IDS[d]] = {"records": n, "head": None, "self_head": None,
                               "last_stamp": None, "liveness": "DARK"}
            continue
        last = recs[-1]
        lasts[d] = last
        ts = parse_ts(last.get("ts", ""))
        age = (now - ts) if ts else None
        live = "LIVE" if (age is not None and age <= STALE_S) else "STALE"
        members[IDS[d]] = {"records": n, "head": last.get("hash"),
                           "self_head": last.get("self_head"),
                           "last_stamp": last.get("ts"), "liveness": live}
    # Completeness (v1.1): the CORE members' latest records inside one
    # window, each citing the other core member. TV is reported, never
    # required: its absence cannot degrade the chain.
    complete = False
    round_ts = None
    if all(d in lasts for d in CORE):
        tss = [parse_ts(lasts[d].get("ts", "")) for d in CORE]
        if all(t is not None for t in tss) and max(tss) - min(tss) <= WINDOW_S:
            cited = True
            for d in CORE:
                peers = set((lasts[d].get("peers") or {}).keys())
                need = set(CORE) - {d}
                # SOV and TV may also ride; only core citations required.
                if not need.issubset(peers):
                    cited = False
            complete = cited
            if complete:
                round_ts = lasts["NIKOLAI"].get("ts")
    state = {
        "chain": "witness-hub",
        "name": "Three-gadget witness hub (QUICK)",
        "baseline": "NP-20261027T185410Z",
        "baseline_chains_to": "NP-20261026T170000Z",
        "members": members,
        "last_complete_round": round_ts,
        "status": "LIVE" if complete else "DEGRADED",
        "complete_now": complete,
        "core_members": ["nikolai", "roach"],
        "tv_gates": False,
        "evidence": "CHECKED",
        "as_of": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "reader": "chainer.py v1.1 on nikolai (read-only)",
    }
    OUT.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    return state


def main():
    if "--once" in sys.argv:
        print(json.dumps(one_pass(), indent=1, sort_keys=True))
        return
    while True:
        try:
            one_pass()
        except Exception:  # noqa: BLE001 — a reader never dies on a bad pass
            pass
        time.sleep(CADENCE_S)


if __name__ == "__main__":
    main()
