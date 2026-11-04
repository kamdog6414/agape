# XCHAIN v1 — Agape module, N-way witness mesh across 5 devices

Date: 2026-10-27 12:20 PDT (America/Los_Angeles)
Author: Groku.2
Scope: additive, reversible, free. Read-only on all external sources
(HCDU-LOG, ledger.yfm, TV muse-state). No reboots, no service
start/restart, no deletions, no paid calls. Tailnet only.
Mandate (Kam, 11:59 AM PDT): "build it straight into agape and across
every device."

## What was built
XCHAIN v1 = N-way cross-signed chain-head witness hub. Each device keeps
its own append-only, hash-chained log at ~/xchain/xchain.jsonl. Each mesh
round, every device appends one record capturing every other device's
latest head plus its own self-head, prev_hash and record hash. Verify
checks the local chain integrity and cross-checks recorded peer heads for
order-consistency against each peer's own chain. Version-aware hashing
preserves and still verifies the existing v0 records on NIKOLAI/ROACH, so
the 15-min routine is not broken.

Backward compatible: v1 verify accepts the legacy --peer-file flag and
still verifies v0 records, so the 15-min routine keeps working.

Runtime script (identical on all 5):
  sha256 = cd9caf1e95db8935903a5b6455b1c017e3db04bc304e653760b3ed44af36085f

Self-head source per device (read-only):
  NIKOLAI = sha256 of HCDU-LOG last line
  ROACH   = sha256(ledger.yfm) + ledger head_sha256
  SOV/SOAP/TV = own chain head (GENESIS:<DEVICE> when empty)

## Agape module placement (<agape>/modules/xchain/)
  NIKOLAI : ~/agape-push/modules/xchain/  (xchain.py -> ~/xchain/xchain.py symlink, + MODULE.md)
  ROACH   : ~/agape-push/modules/xchain/  (symlink to ~/xchain/xchain.py, + MODULE.md)
  SOAP    : ~/agape-push/modules/xchain/  (symlink to ~/xchain/xchain.py, + MODULE.md)
  SOV     : C:\FullCircle\agape\modules\xchain\  (registration copy + MODULE.md; agape_hub.py runs there)
  TV      : no Agape tree present -> module kept at Termux ~/xchain  (/data/data/com.termux/files/home/xchain)
Runtime chain on every device stays at ~/xchain/xchain.jsonl. On
NIKOLAI/ROACH the pre-existing ~/xchain is kept in place untouched aside
from appends, so the 15-min routine keeps working.

## Mesh rounds + verify (2 full symmetric rounds, all 5 devices; +1 live orchestrator round on the 4 ssh/adb-reachable devices)
Per-device verify (own chain + cross-check vs all peers): ALL PASS

  Device   records  head(prefix)        self-head source   verify
  NIKOLAI  7        2983057657d14402    HCDU last-line      PASS
  ROACH    7        1523fb706dec54fc    ledger hash         PASS
  SOV      3        263c0b28d7613768    own chain           PASS
  SOAP     2        33b3bc5708ed7304    own chain           PASS
  TV       3        9511a3e53b4a2c24    own chain           PASS

Cross-check matrix: every device's recorded peer heads are
order-consistent with each peer's own chain (CROSSCHECK OK vs all 4
peers, for all 5 devices). On-device cross-check also run and PASS on
NIKOLAI and ROACH; box-side cross-check PASS for all 5.

## Heartbeats (one test send per device with a running musegadget gadget service)
  NIKOLAI : Sent to your Muse.  rc=0
  ROACH   : Sent to your Muse.  rc=0
  TV      : Sent to your Muse.  rc=0  (homelink-8b4c77, via ~/muse-sdk + MUSEGADGET_SOCKET=~/muse-state/muse.sock)
  SOV     : SKIPPED — no musegadget gadget service (only the Muse desktop app: MuseAuthService/muse-bin); musegadget not installed
  SOAP    : SKIPPED — no musegadget gadget service running
No musegadget service was started or restarted.

## Box-side orchestrator (for the 15-min routine)
  /workspace/xchain/mesh_round.sh
Runs one full round (gather heads -> append on each -> pull chains ->
verify+crosscheck on all 5 -> heartbeats on NIKOLAI/ROACH/TV).
  Usage:  bash /workspace/xchain/mesh_round.sh
  Env:    SKIP_HEARTBEAT=1  to skip the Muse heartbeats
Helper: /workspace/xchain/genpayloads.py (reads heads file, emits per-device base64 round payload)
Reachability note: the orchestrator drives the 4 ssh/adb-reachable
devices (NIKOLAI, ROACH, SOV, TV). SOAP is reachable from the box only
via the agent machineId Shell channel (no tailnet sshd from box yet);
its chain is refreshed out-of-band and left in peers/ for cross-check.
When the SOAP control key / sshd is enabled, add a SOAP wrapper to pick
it up automatically.

## ROLLBACK
Fully reversible, additive only. To undo on any device:
  rm -rf ~/xchain/peers
  rm -rf <agape>/modules/xchain        (NIKOLAI/ROACH/SOAP ~/agape-push/modules/xchain ; SOV C:\FullCircle\agape\modules\xchain)
  # To remove v1 entirely (optional): rm ~/xchain/xchain.py ~/xchain/xchain.jsonl
  # On the box: rm -rf /workspace/xchain /workspace/xchain-v1
No external source was modified; HCDU-LOG, ledger.yfm and TV muse-state
were read/hashed only. Removing the above leaves every device exactly as
before, except the pre-existing ~/xchain v0 chain on NIKOLAI/ROACH which
should be left in place for the 15-min routine.

— Groku.2
