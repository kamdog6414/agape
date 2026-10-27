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

No license file is included yet.
