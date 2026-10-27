Grok Bot - ROUND-SEAT

# Agape round tool v0.3

Part: Conformance. Offline perpetual hackathon loop.
Named point it starts from: NP-20261026T170000Z
(manifest sha256 e605b853d6eea415073da043a65d9f28fb8b715e669d4ece94b0c74bee88e7b7).

Python 3 standard library only. No network. No paid APIs. Plain text out,
black and white only. One round of the loop: open, submit, judge, close,
then the next open.

## What changed in v0.3 (the founder's L-11 ruling, 11:02 AM PDT)

- Round 0 keeps LAWS v1 (laws.py) as its scorer of record. Rounds 1 and
  later judge with LAWS-SEAT's LAWS v2 (laws_v2.py, in ../laws,
  used as delivered): L-11 named_point_hash checks the round's own named
  point AND walks the chain of close manifests back to genesis
  NP-20261026T170000Z (e605b853...7bee88e7b7) with laws_v2.verify_point.
- close writes the LAWS v2 link: "name": <NP id> and
  "supersedes": {"sha256", "np_id", "path", "note"} naming the previous
  point. The v0.2 fields (np_id, prev_np_id, prev_manifest_sha256) stay.
- Every close manifest is kept in a chain dir, one folder per point:
      <chain>/<NP id>/MANIFEST.json  (+ MANIFEST.json.sha256)
  byte-exact copies of close/<NP>.json; genesis is seeded there too.
  Default chain dir is <dir of the round dirs>/chain (runs/chain for runs/).
  A point is never overwritten with different bytes.
- Besides laws_v2's walk, judge requires the round's manifest to still hash
  to the sha256 pinned in round.json at open. The chain proves links, not
  that the point you opened on is the one you judge.
- Conformance receipts get the round's NP via a wrapper (conformance.py is
  run unchanged): <receipt>-np.json records named_point, the NP the receipt
  was stamped with, np_matches_receipt, and the receipt's sha256.
- New commands: chain, conformance-check --np. NP ids never repeat within a
  chain (close waits a second if the stamp is taken).

## What changed in v0.2

- Packages are agape.mod.v0 (GPT Codex - MOD-SEAT, MOD-FORMAT.md).
  Identity is the sha256 of the raw MANIFEST.json bytes, given at submit as
  an external pin. The provisional mod.json format is gone; the fixtures
  are real agape.mod.v0 packages.
- Verification is MOD-SEAT's package.verify_package(package_dir, pin).
  Payload code is never imported or run to verify or judge.
- Order is SORTER-SEAT's sorter.order_round(core, submissions, round_id), which
  calls core.set_order on one round core.
- Offline evidence is namespace-aware: judge --netns re-runs itself under
  `unshare -rn` and records /proc/self/ns/net, /proc/net/dev and
  /proc/net/route from inside the run. /sys/class/net is not used (it shows
  the host sysfs view). If unshare is missing or refused, the evidence file
  says so and the verdict is NOT_PROVEN_OFFLINE.

## Files

    round.py          the CLI
    test_round.py     Round 0 (v1) closes, Round 1 and 2 under LAWS v2, tamper cases
    mods/demo-bw/     good fixture, agape.mod.v0, requires hello-bw
    mods/bad-net-key/ planted-defect fixture, agape.mod.v0 (URL fetch import,
                      fake key line); it must FAIL judging and is never run
    mods/*.MANIFEST.sha256   external pins, kept outside each package

## What it uses (all in this repository)

    ../mod/ROUND0/package.py   verify_package(package_dir, expected_sha256),
                               PackageError, NAMED_POINT, BASE, RUNTIME
    ../sorter/sorter.py        order_round(core, submissions, round_id)
    ../laws/laws.py            PREDICATES, named_point_hash, no_secrets_in_mod,
                               no_network, black_and_white, secret_hits,
                               network_hits, color_hits
    ../base/base.py            open_base, enable, set_order (via Sorter),
                               note_laws, receipts, probe
    ../conformance/conformance.py  is_sensitive, walk_tree, entries_hash, check
    ../laws/laws_v2.py         verify_point, GENESIS_POINT,
                               GENESIS_MANIFEST_SHA256, MAX_DEPTH, and v1's
                               content predicates (it imports laws.py from its
                               own folder; round.py records that laws.py's
                               sha256 as laws_v2_imports_v1)

## Genesis pin

round.py, laws.py and laws_v2.py pin the real genesis manifest sha256
(e605b853...7bee88e7b7). That manifest is not in this repository. The
environment variable AGAPE_GENESIS_SHA256 overrides the pin; test_round.py
and ../demo.py set it, for their child processes only, to a synthetic
genesis manifest they write in a temp directory.

## Commands

The global option --conformance <path> goes before the command.

    pack <moddir> --package package.py --id ID --version V --entry payload/x.py
         --inputs a --outputs b [--requires x,y] [--conflicts z]
        Writes MANIFEST.json for <moddir>/payload/ by the MOD-FORMAT.md
        producer convention, writes the pin to <moddir>.MANIFEST.sha256
        (outside the package), then runs verify_package on it.

    open --np <NP id> --manifest <path> --out <rounddir> [--needs needs.json]
         [--chain <dir>] [--laws-manifest <path>  (Round 0 only)]
        From a close manifest, the needs file must hash to the needs_sha256
        the close manifest names. Round 0 is laws_version v1. Later rounds
        are v2: the manifest is placed in the chain dir (or must already be
        there byte-equal) and becomes the round's laws manifest.

    submit <rounddir> --mod <dir | .zip | .tgz> --sha256 <pin> --seat <SEAT>
           [--member <package folder inside the archive>]
        Copies the package as given (links kept as links) into
        submissions/S-xxx/package/. Archives are unpacked in a temp dir and the
        archive path and sha256 are recorded. Sensitive file names are
        refused and never opened.

    judge <rounddir> --laws laws.py [--laws-v2 laws_v2.py] --package package.py
          --sorter sorter.py --base base.py [--box ROUND-SEAT] [--netns]
        --laws-v2 is required for rounds after Round 0. L-11 evidence lists
        each chain hop with its file, the depth, laws_v2's reason, and for a
        broken chain the link that points at a missing manifest.
        Per submission: verify_package against the pin; the four laws over
        the package (payload laws NOT_RUN if verify failed); conformance
        check of the package against its own MANIFEST.json. Then one round
        core: enable(mod_id, manifest_sha256) for each submission passing all
        of those, order_round, note_laws once. Writes evidence/run-offline.txt,
        evidence/order.json, evidence/S-xxx/*, score-S-xxx.json, sidecars.
        Overall PASS only if verify, four laws, CONFORMS, enable and sorter
        all PASS. Exit 1 on any FAIL.

    close <rounddir> [--chain <dir>]
        FAILs become NEEDs, then close/NP-<stamp>.json with name and
        supersedes, copied to <chain>/<NP>/MANIFEST.json. The next open
        should use that chain copy.
    verify <rounddir>    sidecar, chain link, round dir CONFORMS.
    chain <manifest> --laws-v2 laws_v2.py [--chain <dir>]
        Prints laws_v2 verdict, depth, reason and each hop. Exit 1 if broken.
    conformance-check <base> <dir> --box BOX --out receipt.json --np <NP id>
        Runs conformance.py check unchanged, then writes receipt-np.json
        tying the receipt (by sha256) to the given NP.
