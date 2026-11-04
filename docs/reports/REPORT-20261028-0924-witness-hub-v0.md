# REPORT 2026-10-28 09:24 PDT -- Hackathon witness hub v0 (item D)
Authority: Kam t1515u (2026-10-28 09:12 AM PDT), recommendation (1).
Repo: ~/hackathon/witness-hub/ on NIKOLAI (new; git init). LOCAL ONLY: no remote, nothing pushed, no GitHub.
Commit: a1df135683acc2571bb738a9519a448db4ec6abb (2026-10-28 09:22:44 PDT), author "Grok Bot (for Kam)" set per-commit with -c. Global git config NOT changed.
In-window start stated in README: 2026-10-28 09:22 PDT. Official hackathon window start: UNKNOWN (board says ~10 AM PDT Oct 26, unverified).
Prior work declared in README: THE TRACER, everything before 2026-10-26, and XCHAIN v1 xchain.py (Oct 27; called as an external tool, not copied). Nothing was copied from TRACER.

## Files (MANIFEST.md in repo)
hub/witness_screen.py  8402  fd139aad9f7ce9d7767ac708058ba95601c1634ca157079bf82ba54c1eeb0183
README.md              2779  c48eb7f0fd2ca624681358a547fcf972f5b67163a376584259cf203afa4d25c6
LICENSE (Apache-2.0)  11358  cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30 (= /usr/share/common-licenses/Apache-2.0)
.gitignore               62  f75ffb01c2a9c5e8ed50c5a01b2df584eff4e148aa4d96b527c02ec2971a7686
gadgets/tv/README.md    560  b211c3dbfeeaf30551b69b27a33c942f090740f4a0cf40a0384fae70868a2096 (TV stub doc)
docs/IN-WINDOW.md       445  b9b087513325edc1319389ac69bcb8d133336ffe8754fee170da86149574d6bf

## Behaviour (tested 09:22 PDT)
- python3 -B, stdlib only, no installs, 0 __pycache__. Black/white plain monospace. The optional --html render is black on white inside a <pre>.
- Reads chains read-only. Verification runs the existing ~/xchain/xchain.py verify --peers-dir on temp copies, so the live ~/xchain is never written (NIKOLAI xchain.jsonl sha unchanged across the test runs).
- Live NIKOLAI + fresh Roach copy: both CHAIN OK, crosscheck OK both ways, witness MATCH (latest head) both ways.
- Tamper test (temp copy): Roach CHAIN FAIL "hash mismatch at 4".
- Hanging source: HOLD after the 10 s timeout. TV: always HOLD "offline / stub, not contacted".
- Default Roach source = ~/xchain/peers/ROACH.jsonl, a stale Oct 27 copy. It shows as STALE, and NIKOLAI's crosscheck FAIL is annotated "[peer copy STALE]".

## Left to do (not done)
- A live Roach feed for NIKOLAI. NIKOLAI -> roach@<TAILNET-IP> ssh gives "Permission denied (publickey)". No route or auth was added (hard rule). Kam must choose an existing read-only path, then set WH_ROACH_SRC='cmd:...' or refresh the peers file.
- TV leg (stub, wait for Kam home), Roach-side hub instance (Roach witnessing NIKOLAI from Roach), demo script/video, public repo + push (Kam decision).
- Test copies used: ~/grok-reports/.staging/ (wh-src.tar, ROACH.jsonl copy, witness.html, tamper temp dir). Left in place (delete-nothing rule); safe to remove.
Rollback: rm -rf ~/hackathon/witness-hub   (nothing else references it)
