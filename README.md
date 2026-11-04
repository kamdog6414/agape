# Agape

Agape is a small, offline method for building software in rounds with
several independent builders, where every step can be checked by hash
instead of by opinion.

It has three parts:

    Base      a hash-pinned shared core. A mod is known only by an id and
              the sha256 of its raw MANIFEST.json bytes. Every enable,
              disable and load-order change returns a receipt.
    Manager   a receipted mod manager on top of Base: install (after the
              package verifies against its external pin), enable, disable.
    Rounds    a round opens from a named point (a manifest whose sha256 is
              known), takes package submissions, judges them with fixed
              law predicates, and closes into a new named point that names
              the one it supersedes. The chain of points walks back to a
              genesis point.

Judging is deterministic code. There are no AI grading scores: a law is a
predicate over the package bytes (named point hash, no secrets in the mod,
no network capability, black and white output), plus package verification,
a conformance check and the Sorter's load order. A result is PASS or FAIL
with the evidence written next to it.

Python 3 standard library only. No network, no paid services, no
dependencies.

## Layout

    base/          Base v1 core (base.py), interface, tests
    manager/       Manager v1 (manager.py), notes, tests
    mod/ROUND0/    agape.mod.v0 format (MOD-FORMAT.md), package.py
                   verifier, and the hello-bw example package with its
                   external pin (packages/hello-bw.MANIFEST.sha256)
    sorter/        load order and conflict check over requires/conflicts
    laws/          law predicates v1 (laws.py) and v2 (laws_v2.py, adds the
                   named-point chain walk), scorers, tests
    conformance/   tree manifest and conformance checker used by rounds
    round/         round tool (open, submit, judge, close, verify, chain,
                   pack), test, demo-bw and bad-net-key fixtures
    memory-retro/  an agape.mod.v0 package: a deterministic scorer for
                   memory continuity and context usage, run here only on
                   synthetic fixtures
    hub/muse-hub/  the witness hub: round runner, chainer, status
    xchain/        the chain: v0 runner, v1 runtime with baseline +
                   crosscheck, payload helpers, tests
    gadgets/       per-gadget code: roach/ (satellite checker, verify
                   library, tamper evidence), hazels-tv/ (link watchdog)
    docs/          ATOM-BASELINE.md (method) and reports/ (dated build
                   receipts for xchain, musehub, the witness hub)
    demo.py        end-to-end demo
    run_tests.py   runs every test and the demo

## Run it

    python3 -B demo.py
    python3 -B run_tests.py

demo.py works only in a temp directory and removes it. It:

    1. verifies hello-bw with package.py against its external pin, and
       shows that a wrong pin is refused;
    2. on a fresh in-memory Base, has the Manager install hello-bw from the
       package, enable it, and disable it, printing each receipt;
    3. opens Round 0 from a synthetic genesis named point, submits
       hello-bw, demo-bw (requires hello-bw) and bad-net-key (a planted
       defect: a URL fetch import and a fake key line, never executed),
       judges, prints each score and the Sorter order, and closes the
       round into a new named point;
    4. runs memory-retro on its clean synthetic corpus and on one planted
       defect, and shows the defect is counted.

run_tests.py runs each suite under python -B with
PYTHONDONTWRITEBYTECODE=1, so no bytecode caches are written.

On Linux with unprivileged user namespaces, round judging can record
offline evidence from a child network namespace (judge --netns). Where
unshare is missing or refused, the evidence says so and the verdict is
NOT_PROVEN_OFFLINE; the tests accept either.

## The witness hub (QUICK)

Three small machines watch each other keep a hash chain, so no single
machine's record has to be taken on its own word.

```
NIKOLAI   a Linux desktop. Runs the hub: every 600 seconds it collects
          each gadget's current chain head, stamps one XCHAIN round
          across all of them, and verifies every stamped chain on the
          box that produced it.
Roach     a Linux desktop. Stamps its own chain locally, and runs an
          independent satellite checker (below).
hazels-tv a Fire TV. The third gadget. Reached through Roach; stamps
          whenever it answers. It is an optional member: the TV gets
          turned off, and a dark TV is a normal state, never a fault.
```

Core members are NIKOLAI and Roach. A round is complete when every core
member has stamped inside one window and each stamp cites the others.
A member that does not answer is omitted from that round — partial
rounds are honest rounds. A member that stamps but fails verification
fails the round: absence is fine, bad evidence is not.

The chainer (hub/muse-hub/chainer.py) reads the members' chain tails
and maintains the public chain state: members, current heads, the last
complete round. It never writes a member's ledger. Read-only on every
member, always.

A fourth witness stands outside the hub: the pi-2 post on SAT, a laptop
running an independent witness on a two-minute cadence. It watches the
movement; it is not a hub member and does not stamp hub rounds.

Status at the time of writing (2026-11-04): hub LIVE, rounds passing
with all three gadgets stamping. The hub chain is anchored at named
point NP-20261027T185410Z, which chains to genesis NP-20261026T170000Z.

Code in this repository: hub/muse-hub/ (round runner, chainer, status),
gadgets/roach/ (satellite), gadgets/hazels-tv/ (TV link watchdog),
docs/reports/ (build receipts for xchain v0/v1, musehub v0, the hub).

## XCHAIN and the atom baseline

XCHAIN (xchain/) is the chain the hub stamps. One implementation,
deployed on every gadget:

- Each device keeps its own append-only chain of round records
  (xchain.jsonl). A record names the device, its previous record's
  hash, and the current heads of every peer it has seen.
- A round is the set of records stamped inside one window, each citing
  the others' heads. Verification is recompute: re-hash every record,
  check every link, check that the cited peer heads match the peers'
  own chains. No trust, no scores — the hashes agree or they do not.
- Sources are read-only and the chain is additive only. Nothing is
  edited or deleted; a correction is a new record that supersedes.

The atom baseline is the fixed starting configuration the chains are
checked against: one baseline manifest, pinned in code, verified by
xchain/v1/test_baseline.sh. If a device's baseline does not match the
pin, the round does not proceed.

The satellite (gadgets/roach/satellite.py) is a second, independent
checker. It pulls the coordinator's ledger and the peer chains
read-only over a signed link, verifies them itself, cross-checks the
other satellite's verdicts, and appends verdicts only to its own
hash-chained log. Its flags are plain: DISAGREE, ATOM_BREAK, STALE,
LEDGER_BREAK. Two checkers that do not share code paths agreeing on a
chain is the strongest statement this system makes.

Anchor root, 2026-11-04 (method only): six anchor records from the
fleet's shared-room seal round — three events and three bundles — were
sorted by hash and hashed as one compact JSON array (UTF-8, no
trailing newline):

    sha256(json_array_of_6_hashes_sorted) =
    07b1bb90149ff0e24e4dbf5902dcbfdbf3d81f89132cd572cecd25a7fb2b56ce

Four seats recomputed the same root independently and agreed; the one
divergent seal was traced to a different encoding of the same six
hashes and reconciled as a separate record, not edited. The root is an
address for that moment of agreement. The records it names are not in
this repository.

## Run / replay the hub

Everything is Python 3 standard library. No network services, no paid
APIs, no dependencies to install.

Baseline first — prove the starting configuration before any round:

```
xchain/v1/test_baseline.sh        # atom baseline tests
python3 -B run_tests.py           # the Agape suite (repo root)
```

One hub round, on the hub machine (NIKOLAI's role):

```
python3 hub/muse-hub/hub_round.py   # collects heads, stamps one round,
                                    # verifies each chain on its own box
python3 hub/muse-hub/hub_status.py  # members, heads, last complete round
```

Run resident, hub_round.py repeats on its 600-second cadence and logs
one line per round. Roach's satellite runs on its own cadence and
appends one verdict line per check to its verdicts log.

Replay is the verification path run backwards: take any recorded round,
recompute every hash and every link from the raw records, and compare
against the heads the round claimed. The chainer does this continuously
against the live chains. To see the failure mode, copy one round record,
change one byte, and re-verify: the recompute disagrees and the record
is flagged. A worked example ships in gadgets/roach/tamper-detect-
20261104T062931Z.json — one altered record, detected.

## Genesis named point

The real genesis point is NP-20261026T170000Z, a manifest whose sha256 is

    e605b853d6eea415073da043a65d9f28fb8b715e669d4ece94b0c74bee88e7b7

That manifest is not in this repository: it lists file paths on private
machines. The code pins its sha256 by default. The environment variable
AGAPE_GENESIS_SHA256 overrides the pin; demo.py and round/test_round.py
set it, for their child processes only, to a synthetic genesis manifest
with the same name that they write in a temp directory. Two tests that
can check the real manifest (laws/test_laws_v2.py and
conformance/test_conformance.py) read it only if AGAPE_GENESIS_MANIFEST
points at a copy, and otherwise skip that one check.

## Prior work and new point

In-window work begins at named point NP-20261026T170000Z
(2026-10-26 17:00:00 UTC, 10:00 PDT), genesis manifest sha256
e605b853d6eea415073da043a65d9f28fb8b715e669d4ece94b0c74bee88e7b7.

Before the new point (prior work, not in this repository):

    - The genesis manifest itself. It records a snapshot of 20 earlier
      files taken at 17:00:03 UTC (an earlier round-0 core, a demo runner,
      a spec graph and a standard document) and supersedes a 6-file
      pre-kickoff baseline. None of the files in this repository appear
      in that snapshot.
    - The idea of named points and hash pins (the
      fullcircle.named-point.v1 manifest format string used here comes
      from that earlier work).

- FC-Link (fclink 1.x, 2026-10-23 to 2026-10-25): the signed,
  hash-stamped file link between machines that the hub's read lanes
  and the satellite's pulls still ride on. Prior work; the hub was
  built on top of it, not instead of it.

- The first cross-witness rounds (2026-10-25): two machines checking
  each other's chain heads and filing the comparison. The witness hub
  is this idea made resident and continuous.

- The Fire TV hub app (built 2026-10-26, before kickoff): the Android
  helper that lets a television hold a chain and stamp rounds as a
  gadget. Prior work. hazels-tv's watchdog in this repository
  (gadgets/hazels-tv/) is in-window; the app itself is cited here, not
  shipped.

- The three machines themselves: salvaged and refurbished desktops
  and a television, in service before the event. The hardware is prior
  work by definition; what was built in-window is the software and the
  method above.

After the new point (in-window, everything in this repository):

    component                    evidence of date (2026-10-26 PDT unless noted)
    mod/ROUND0/MOD-FORMAT.md     format text dated 17:39:50 UTC (10:39 PDT)
    hello-bw package             manifest created_utc 17:45:52 UTC
    laws/ PREDICATES.md,         file times 10:40 PDT
      test_laws.py
    laws/laws.py                 file time 10:56 PDT
    laws/laws_v2.py,             file times 11:05 to 11:06 PDT
      test_laws_v2.py,
      PREDICATES-V2.md
    conformance/                 file times 10:24 to 10:25 PDT
    sorter/                      file times 10:50 PDT
    round/round.py v0.3          file time 11:12 PDT (18:12 UTC)
    round/mods/demo-bw           manifest created_utc 17:57:00 UTC
    base/ Base v1                shipped 2026-10-27 00:10:27 UTC (17:10 PDT)
    manager/ Manager v1          built against Base v1, so after it
    memory-retro/                file time 20:35 PDT
    demo.py, run_tests.py,       written 2026-10-26 PDT for this repository
      this README

Every component also names NP-20261026T170000Z or is built against a
component that does. Base v0 (whose calls Base v1 keeps) is not in this
repository, and its ship time was not checked for this README.

What can and cannot be verified: the dates above are file modification
times and timestamps written inside the files and manifests at the time.
They are consistent with each other and all fall after 17:00 UTC, but
they are not cryptographic proof of when the work was done. The genesis
manifest sha256 is verifiable only by someone holding that manifest. This
repository is a single commit; it does not carry the in-window history.

Changes made for this public copy: builder machine and seat names were
replaced with neutral role names (BASE-SEAT, MANAGER-SEAT, MOD-SEAT,
SORTER-SEAT, LAWS-SEAT, ROUND-SEAT; BOX-A..BOX-D for machines), private
paths were removed, tests were pointed at in-tree files and synthetic
fixtures, and the affected package manifests were re-pinned, so the pins
here differ from the originals. Model names in file headers are kept as
attribution of who wrote each part.

## License

MIT — see LICENSE.

Copyright 2026 Kamron Noah Dabe / FullCircle.
