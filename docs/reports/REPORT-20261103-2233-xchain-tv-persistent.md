# XCHAIN TV link made persistent (authorized_by pt1854u)
1. Roach watchdog: new ~/xchain/tv-link/watchdog.sh plus systemd --user xchain-tv-link.timer (OnBootSec=30s, every 60s). If <LAN-IP>:5555 isn't in `device` state it runs adb disconnect/connect, and logs state changes to ~/xchain/tv-link/link.log. Rollback: Roach ~/xchain/tv-link/ROLLBACK.txt (new files only).
2. NIKOLAI xchain-coord.timer (:15/:45) already runs `local_round.sh --live --tv`, so nothing changed. coord.py treats an unreachable TV as "HOLD (unreachable)" (INTERMITTENT), never FAIL. No alert path.
3. TV-side boot persistence: Termux:Boot is NOT installed (no ~/.termux/boot). Adding it would mean a new install, so it wasn't done. It isn't needed: the coordinator drives the TV append via roach-adb `run-as com.termux`. The only requirement is that adb debugging is still on after a TV reboot (Fire TV keeps it).
4. Linger=yes on Roach and NIKOLAI, so the timers survive a reboot without login. No sudo was needed.
5. Proof: 22:31:5x PST adb disconnect; watchdog logged "22:32:28 -> reconnect -> device". Round 20261104T063252Z (hash f0876d87005ad487): TV PASS, 308 records, head a2aa29f023a9, OVERALL PASS, hold=-.
Backup: ~/xchain/coord/bak-tv-20261103T2230/rounds.jsonl.pre-persist. Not touched: sealed pids, ports 18872/:8900, ledger.yfm, HCDU-LOG, BASELINE-atom.json.
