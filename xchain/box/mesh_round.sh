#!/bin/bash
# XCHAIN v1 — box-side mesh orchestrator (one full round + verify + heartbeats).
# Additive, read-only on external sources. For the 15-min routine.
# Usage:  bash /workspace/xchain/mesh_round.sh
# Env:    SKIP_HEARTBEAT=1 to skip Muse heartbeats.
set -u
W=/workspace
D=$W/xchain
PEERS=$D/peers
mkdir -p "$PEERS"
TS=$(date -u +%Y%m%dT%H%M%SZ)
log(){ echo "[$(date -u +%H:%M:%SZ)] $*"; }

NIK="$W/nik.sh"
RCH="$W/rch.sh"
SOV="$W/sov.sh"
PYV="python C:/Users/<user>/xchain/xchain.py"
PYN="python3 -B ~/xchain/xchain.py"
# TV via Roach adb + Termux
TVADB="adb -s <LAN-IP>:5555 shell run-as com.termux"
TVENV="env XCHAIN_DEVICE=TV XCHAIN_DIR=/data/data/com.termux/files/home/xchain HOME=/data/data/com.termux/files/home /data/data/com.termux/files/usr/bin/python -B /data/data/com.termux/files/home/xchain/xchain.py"
TVMUSE="env PYTHONPATH=/data/data/com.termux/files/home/muse-sdk HOME=/data/data/com.termux/files/home MUSEGADGET_STATE_DIR=/data/data/com.termux/files/home/muse-state MUSEGADGET_SOCKET=/data/data/com.termux/files/home/muse-state/muse.sock /data/data/com.termux/files/usr/bin/python -m musegadget"

HEADS=$D/heads.$TS
: > "$HEADS"
add_head(){ [ -n "$2" ] && echo "$1 $2" >> "$HEADS"; }

log "Phase 1: gather heads"
add_head NIKOLAI "$($NIK "$PYN head" 2>/dev/null)"
add_head ROACH   "$($RCH "$PYN head" 2>/dev/null)"
add_head SOV     "$($SOV "$PYV head" 2>/dev/null | tr -d '\r')"
add_head TV      "$(timeout 30 $RCH "$TVADB $TVENV head" 2>/dev/null | tr -d '\r')"
# SOAP: reachable only via the agent machineId Shell channel; handled out-of-band.
cat "$HEADS"

log "Phase 2: payloads"
python3 -B "$D/genpayloads.py" "$HEADS" > "$D/pay.$TS"

log "Phase 3: append"
getp(){ awk -v d="$1" '$1==d{print $2}' "$D/pay.$TS"; }
[ -n "$(getp NIKOLAI)" ] && $NIK "$PYN append --round-b64 $(getp NIKOLAI)" >/dev/null && log "NIKOLAI appended"
[ -n "$(getp ROACH)" ]   && $RCH "$PYN append --round-b64 $(getp ROACH)"   >/dev/null && log "ROACH appended"
[ -n "$(getp SOV)" ]     && $SOV "$PYV append --round-b64 $(getp SOV)"     >/dev/null && log "SOV appended"
[ -n "$(getp TV)" ]      && timeout 30 $RCH "$TVADB $TVENV append --round-b64 $(getp TV)" >/dev/null && log "TV appended"

log "Phase 4: pull chains + verify"
# NIKOLAI: nik.sh truncates large outputs, so pull in 16 KB chunks and sha-check
nikpull(){ local out=$(mktemp) want sz n i; : > "$out"
  read -r want sz < <($NIK "sha256sum ~/xchain/xchain.jsonl | cut -d' ' -f1; stat -c%s ~/xchain/xchain.jsonl" </dev/null 2>/dev/null | tr '\n' ' ')
  n=$(( (sz + 16383) / 16384 ))
  for ((i=0;i<n;i++)); do $NIK "dd if=\$HOME/xchain/xchain.jsonl bs=16384 skip=$i count=1 2>/dev/null | base64 -w0" </dev/null 2>/dev/null | base64 -d >> "$out"; done
  if [ "$(sha256sum "$out" | cut -d' ' -f1)" = "$want" ]; then cp "$out" "$PEERS/NIKOLAI.jsonl"; else log "NIKOLAI pull sha mismatch"; $NIK "cat ~/xchain/xchain.jsonl" > "$PEERS/NIKOLAI.jsonl" 2>/dev/null; fi
  rm -f "$out"; }
nikpull
$RCH "cat ~/xchain/xchain.jsonl" > "$PEERS/ROACH.jsonl" 2>/dev/null
$SOV "python -c \"import sys;sys.stdout.write(open(r'C:/Users/<user>/xchain/xchain.jsonl').read())\"" > "$PEERS/SOV.jsonl" 2>/dev/null
timeout 30 $RCH "adb -s <LAN-IP>:5555 exec-out run-as com.termux cat files/home/xchain/xchain.jsonl" > "$PEERS/TV.jsonl" 2>/dev/null
ROUNDS=$D/rounds.jsonl
VERIFY_RC=0
# SOAP.jsonl: refreshed out-of-band via the agent channel (CopyToBox). Left in place if present.
for dev in NIKOLAI ROACH SOV SOAP TV; do
  f="$PEERS/$dev.jsonl"
  [ -s "$f" ] || { echo "$dev: HOLD (no chain)"; continue; }
  tmp=$(mktemp -d); cp "$f" "$tmp/xchain.jsonl"
  XCHAIN_DEVICE=$dev XCHAIN_DIR=$tmp python3 -B "$W/xchain-v1/xchain.py" verify --peers-dir "$PEERS" --rounds "$ROUNDS" > "$tmp/out" 2>&1 || VERIFY_RC=1
  sed "s/^/$dev: /" "$tmp/out"
  rm -rf "$tmp"
done
# v1.1: witnessed-tip round record (round ts + per-device head n/hash), append-only,
# hash-chained in $ROUNDS. Only recorded when every pulled chain passed, so a
# bad pull can never become a witnessed tip.
if [ "$VERIFY_RC" = 0 ]; then
  python3 -B "$W/xchain-v1/xchain.py" record-round --rounds "$ROUNDS" --peers-dir "$PEERS" --round "$TS" | sed 's/^/round: /'
else
  log "verify/crosscheck FAIL -> round not recorded as witnessed"
fi
# ATOM baseline check (additive, read-only). BROKEN => round FAIL (exit 1).
ATOM_RC=0
ATOM_OUT=$(python3 -B "$W/xchain-v1/xchain.py" baseline --manifest "$D/baselines/BASELINE-atom.json" --peers-dir "$PEERS" 2>&1) || ATOM_RC=1
echo "$ATOM_OUT" | sed "s/^/atom: /"
ATOM_LINE=$(echo "$ATOM_OUT" | awk -F'ATOM SUMMARY: ' '/ATOM SUMMARY: /{print $2}')
[ -n "$ATOM_LINE" ] || ATOM_LINE="broken (manifest)"
echo "ATOM: $ATOM_LINE   (include as '| atom $ATOM_LINE' in mesh_log line; broken => overall FAIL)"

if [ "${SKIP_HEARTBEAT:-0}" != "1" ]; then
  log "Phase 5: heartbeats (NIKOLAI, ROACH, TV)"
  $NIK "musegadget send-user-msg 'XCHAIN v1 heartbeat NIKOLAI $TS'" 2>&1 | sed 's/^/NIKOLAI hb: /'
  $RCH "musegadget send-user-msg 'XCHAIN v1 heartbeat ROACH $TS'" 2>&1 | sed 's/^/ROACH hb: /'
  timeout 30 $RCH "$TVADB $TVMUSE send-user-msg 'XCHAIN v1 heartbeat TV $TS'" 2>&1 | sed 's/^/TV hb: /'
fi
log "round $TS complete"
[ "$ATOM_RC" = 0 ] || { log "ATOM BROKEN -> round FAIL"; exit 1; }
[ "$VERIFY_RC" = 0 ] || { log "VERIFY/CROSSCHECK FAIL -> round FAIL"; exit 1; }
log "OVERALL PASS (TV HOLD if no chain)"
