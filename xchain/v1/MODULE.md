# Agape module: xchain (XCHAIN v1)

N-way cross-signed chain-head witness hub across the FullCircle mesh
(NIKOLAI, ROACH, SOV, SOAP, TV). Additive, read-only on all external
sources (HCDU-LOG, ledger.yfm). Each device keeps a local hash-chained
append-only log at ~/xchain/xchain.jsonl recording every peer's latest
head per mesh round.

Runtime lives at ~/xchain/xchain.py (kept in place so the 15-min routine
keeps working). This module dir holds a reference to that runtime; do not
fork it.

Commands:
  python -B xchain.py whichbox          # device identity
  python -B xchain.py head              # this device's self head
  python -B xchain.py append --peers '<json>' [--self-head H]
  python -B xchain.py verify [--peers-dir DIR]

Self-head source per device:
  NIKOLAI = sha256 of HCDU-LOG last line (read only)
  ROACH   = sha256(ledger.yfm) + ledger head_sha256 (read only)
  SOV/SOAP/TV = own chain head (GENESIS:<DEVICE> when empty)

Orchestrated from the box via /workspace/xchain/mesh_round.sh.
— Groku.2
