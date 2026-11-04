# XCHAIN NIKOLAI coordinator: staged, NOT active (2026-11-03, PST)
Author: Grok Bot. The coordinator is not scheduled. No records were appended and no rounds were recorded.

## Built (RECEIPT)
~/xchain/coord/ on NIKOLAI:
- local_round.sh  cf859ddab271f7a11b15ed4d5e5623b31ebf47135da5d509b51b2568f01c04f1 (flock + nice wrapper)
- coord.py        f7d6e2a56e01801adc54fadd4dd87e4d0a57d27044d1a22d2b20b82bb9fc7928
- xchain_v11.py   5135b68fc29b071b19ef0c644e58e19f00b12d45ba42a0404e704cc338b3e9c0 (the box's xchain-v1/xchain.py, unchanged)
- genpayloads.py  35423655a284e80294b17845cf4552f570c80daf6335a7466843796f1fcb1354 (the box's copy, unchanged)
- rounds.jsonl    2377a2a968e4eda12fe356681ab20e569020c5167906a5b1e7b40f023045096a (seeded from the box: 54 lines, tip b66c5bc0)
- BASELINE-atom.json and .sha256  321fe6a4... (frozen copy; SAT is not in it)
- dryrun-20261104T062001Z.txt  0e90a800c300a62f139fe3ba3a0d23f48a9ba020e5f242550f3f15a80774b230 (this is the receipt)
- UNKNOWN: lib/xchain.py, peers/ and receipts/ were already in ~/xchain/coord at 22:17:33 PST, before my copies landed. They were probably created by another agent. I did not touch them.

SAT (box route, additive): ~/xchain/xchain.py and ~/agape-push/modules/xchain/{xchain.py,MODULE.md}. xchain.py is the Agape module copy, sha cd9caf1e.... With XCHAIN_DEVICE=SAT, head returns GENESIS:SAT. No chain file was created.

## Phases
These match mesh_round.sh: FC-Link probe -> heads -> genpayloads -> append (only with --live) -> pull -> verify --rounds coord ledger -> record-round (only with --live and only if all checks pass) -> atom baseline.
- Required peers: NIKOLAI, ROACH, SOV, SOAP.
- Intermittent peers (HOLD, never FAIL): TV, SAT. TV is skipped unless --tv is set.

## Dry-run 06:20Z (22:20 PST)
- NIKOLAI: local route, 680 records, PASS, atom OK.
- ROACH: ssh, 671 records, PASS, atom OK.
- SOV: UNREACHABLE. ssh as <user> from NIKOLAI is denied (publickey). FC-Link health-ok.
- SOAP: UNREACHABLE. Port 22 is closed. FC-Link health-ok.
- SAT: HOLD. The cable alias gets "no route", and the tailnet host key is not in known_hosts.
- TV: HOLD (flag off).
- Overall: FAIL, only because SOV and SOAP have no route. The witnessed-tip check passed for 36 tips.

## Transports
FC-Link 1.3.3 offers health, files (inbox/outbox only), and sha256/verify jobs. It has no exec verb, so it cannot run head or append. coord.py will fetch xchain-<DEV>.jsonl from a peer's outbox over signed FC-Link if a peer ever publishes it there.

## Needs Kam's explicit word to go live
1. A route from NIKOLAI to SOV for head/append/pull. Options: add NIKOLAI's pubkey to SOV authorized_keys, or approve a new signed FC-Link verb (for example xchain-head/xchain-append), or approve SOV publishing its chain to its FC-Link outbox.
2. A route from NIKOLAI to SOAP. Either enable Remote Login on the Mac plus an authorized_keys entry, or approve the FC-Link verb or outbox publishing.
3. SAT from NIKOLAI: a known_hosts entry and an authorized key, or a hop through the box.
4. TV writes from NIKOLAI (--tv --live through Roach adb).
5. A systemd user timer for coord/local_round.sh. Note that a separate read-only xchain-round.timer (~/xchain/local_round.sh, every 15 min) is ALREADY active on NIKOLAI.
6. Switching the box routine to backup/witness mode, and deciding which side's rounds.jsonl is canonical. Two writers would fork the ledger.

Rollback: rm -rf ~/xchain/coord   (SAT: rm -rf ~/xchain ~/agape-push/modules/xchain on SAT)
