FULLCIRCLE  --  THREE-GADGET WITNESS HUB  --  SUBMISSION 2026-11-04
=====================================================================
Meta Global AI Developer Hackathon. Submissions close 2026-11-04 6:00 PM PST.
Plain text. Black and white. Nothing is believed unless it re-hashes.
Verdicts everywhere: HOLDS / FAIL / UNKNOWN. Unverifiable = UNKNOWN.

STATUS OF THIS FOLDER
---------------------
  PUBLIC. This folder is part of github.com/kamdog6414/agape,
  main @ ca32251172bf5122b11449a01a2ae81b1b965659, pushed
  2026-11-04 13:13 PST on the founder's order, hashes left in.
  The 3-minute video is still TODO: filming 2026-11-04 afternoon.

1. WITNESS HUB (three gadgets)
------------------------------
  NIKOLAI  Muse gadget   hash chain ~/xchain/xchain.jsonl
  ROACH    Muse gadget   hash chain, read via a read-only source
  hazels-tv third gadget, display hub; shown as HOLD (stub) in v0
  Each gadget's latest record carries the other gadget's head:
  NIKOLAI and ROACH cross-witness (MATCH / NOT FOUND). The hub runs
  xchain verify on private temp copies; live chains are never written.
  Code: ../hub/witness_screen.py   Run: python3 -B hub/witness_screen.py

2. XCHAIN ATOM BASELINE
-----------------------
  BASELINE-atom.json (NIKOLAI ~/xchain/baselines/) sha256
  321fe6a4fc782021e187afbf919eb39ea29fde1c9ad269c241a78c590185fa4a
  Read only; not copied here. XCHAIN v1 code itself is dated
  2026-10-27 and is not included in this folder.

3. AGAPE ETA TIMER
------------------
  ~/agape-eta on NIKOLAI. Headless, stdlib, no LLM. Forecasts job ETAs,
  scores itself, learns calibration. systemd timer at low priority
  (Nice=19, MemoryMax=128M, idle IO).
  CONFIG GATE: "the configuration run must run the configuration
  qualified."  eta_run.py gate re-hashes every pinned file and prints
    QUALIFIED 48b42a2063214bc8ff2c5ecfaf0d1865b82ef3c7bfc0465573b876b20e356f7e
  (QUALIFIED.json qualified_at 2026-11-04 11:17:50 PST, agape-eta 0.4.0-gate)
  Re-checked 2026-11-04 ~12:00 PST: exit 0. Code copy: code/agape-eta/

4. SAT OFFLINE IMPLANT
----------------------
  SAT: Pentium P6100, 2 cores, ~1.9 GB RAM, 320 GB HDD, Ubuntu 26.04.1,
  Python 3.14.4. Works with ethernet unplugged.
  ~/fieldkit/implant-20261104/ holds an 11 GB offline Wikipedia db
  (sha256 c2646fc18f4a5003608cbbcd79374230cf8c01575e6c01ca79f6ad34dbd23dad,
  built on Roach, byte-identical on SAT), declass corpus 57/57,
  crypto-lab, forensics, and a hash-chained RECEIPTS.jsonl.
    cd ~/fieldkit/implant-20261104 && python3 verify.py
  Full run 2026-11-04 ~11:58 PST: INTEGRITY HOLDS, failures=0,
  174 receipts, head 0a73ea74e900a26f8174b86cee5f1d834a45fd65476a8e319162a0e9a912e770
  Baseline named SAT-2GB by Kam 11:51 AM PST: BASELINE-SAT-2GB.json.
  db PRAGMA quick_check: UNKNOWN (stopped at Kam's choice).
  Code copy: code/sat-implant/verify.py

5. CASTOR
---------
  Castor is the baseline Kam named at the anchor seal (board,
  2026-11-04 7:56-8:33 AM PST), with seals from several seats; a Castor
  operator v1 was staged by NIKOLAI-2. Castor bench check receipt:
  REPORT-20261026-0032-castor-bench-check.md (see RECEIPTS-INDEX.txt).
  Castor code is not in this folder. Details beyond the receipts: UNKNOWN.

PRIOR WORK vs BUILT DURING THE EVENT (Oct 26 - Nov 4, 2026)
-----------------------------------------------------------
  PRIOR WORK (before 2026-10-26, declared, not demoed as new):
    fclink / FC-Link SDK, GECK kit, ghostie models, HCDU disk,
    AGAPE TV app build, THE TRACER and its 2026-10-25 replay caches.
  BUILT DURING THE EVENT:
    2026-10-27  XCHAIN v1 (pre-existing to this repo, used externally)
    2026-10-28  witness hub v0 (this repo, first commit a1df135)
    2026-10-26..11-04  receipts in RECEIPTS-INDEX.txt
    2026-11-04  agape-eta 0.4.0 config gate, SAT implant + SAT-2GB baseline
  Official window start: UNKNOWN in this repo (board says ~10 AM PDT 10-26).
  Exact creation date of each item above beyond the receipts: UNKNOWN.

FILES
-----
  README.md            this file
  RECEIPTS-INDEX.txt   sha256, bytes, path of NIKOLAI ~/grok-reports 20261026-20261104
  code/agape-eta/      ETA code, units, QUALIFIED.json, SHA256SUMS
  code/sat-implant/verify.py   SAT implant verifier (stdlib, offline)
  SHA256SUMS           sha256 of every file in this folder
No keys, tokens, credentials, or ~/.ssh content are included.
