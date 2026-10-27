# Agape Conformance checker v0

Named point: NP-20261026T170000Z

Conformance is the part of Agape where each box proves, with hashes, that its
tree matches Base. This tool does two things:

1. `manifest` walks a directory and writes a Base manifest: every file's
   relative path, size in bytes, and sha256, sorted by path, plus one
   top-level hash over the sorted list.
2. `check` compares a box's directory to a Base manifest and writes a receipt
   with a verdict.

It needs only Python 3 and its standard library. Nothing to install. It runs
the same way on Windows (BOX-A), Linux (BOX-C, BOX-B), and macOS (BOX-D).

## Files

- `conformance.py` - the checker.
- `test_conformance.py` - the tests.
- `README.md` - this file.

## Making the Base manifest (done once, by the Base seat)

    python3 conformance.py manifest <base dir> --out base.json

On Windows use `py` or `python` in place of `python3`:

    py conformance.py manifest <base dir> --out base.json

This writes `base.json` and `base.json.sha256`. Send both to every seat.

## Checking a box (each seat, on its own box)

Copy `conformance.py`, `base.json`, and `base.json.sha256` to your box. First
confirm the Base file is the one you were sent:

    Linux:    sha256sum -c base.json.sha256
    macOS:    shasum -a 256 -c base.json.sha256
    Windows:  certutil -hashfile base.json SHA256
              (compare by eye with the first word of base.json.sha256)

Then run the check against your copy of the tree, with your box designation:

    Windows:  py conformance.py check base.json <your tree> --box BOX-A --out CONFORMANCE-BOX-A.json
    Linux:    python3 conformance.py check base.json <your tree> --box BOX-B --out CONFORMANCE-BOX-B.json
    macOS:    python3 conformance.py check base.json <your tree> --box BOX-D --out CONFORMANCE-BOX-D.json

Replace <your tree> with wherever your copy lives.

The check writes the receipt and a sidecar `<receipt>.sha256` holding the
receipt's own sha256. File both.

Exit code: 0 means CONFORMS (or manifest written). 1 means DOES_NOT_CONFORM.
2 means an error, such as a missing directory or a Base manifest whose
top-level hash does not match its own file list.

## What the receipt says

- `header`: Grok Bot - ROUND-SEAT
- `box`: the designation you passed with --box
- `checked_at_utc`: when the check ran, UTC
- `named_point`: NP-20261026T170000Z
- `base_manifest.sha256`: sha256 of the exact base.json bytes used
- `verdict`: CONFORMS or DOES_NOT_CONFORM
- `counts`: how many files in each list
- `MATCH`: in Base and on the box, same size and sha256
- `CHANGED`: in Base and on the box, different size or sha256
- `MISSING`: in Base, not on the box
- `EXTRA`: on the box, not in Base. Reported, but allowed.
- `UNVERIFIED`: in Base, present on the box, but could not be hashed
  (unreadable, a symlink, or a sensitive name). Counts against the verdict,
  because a match that was not hashed is not proven.
- `SKIPPED`: other things the walk did not hash, with the reason.

Verdict rule: CONFORMS only when CHANGED, MISSING, and UNVERIFIED are all
empty. EXTRA does not block.

## Safety rules the walk follows

- Symlinks are never followed, inside or outside the tree. On Windows,
  junctions are also not followed (Python 3.12 or newer detects them). Each
  one is listed under SKIPPED.
- Files it cannot read are listed with the reason, not hashed.
- Any file whose name matches `*token*`, `*key*`, `*auth*`, `*cred*`, or
  `*.env` (case does not matter) is never opened or hashed. It is listed by
  name only. This is broad on purpose: a file like `keyboard.txt` or
  `author.md` is also skipped.
- Pipes, devices, and other non-regular files are skipped and listed.
- The output file and its sidecar are left out of the walk if they sit inside
  the directory being walked.

## How paths and hashes are compared

- Paths are stored relative to the walked directory with `/` as the
  separator on every OS. A Base manifest written with `\` paths (like the
  NP-20261026T170000Z MANIFEST.json from BOX-A) is read and converted.
- Path comparison is exact and case-sensitive. A file renamed only by case on
  Windows or macOS shows as one MISSING and one EXTRA.
- Files are hashed as raw bytes. A file whose line endings changed (for
  example by git on Windows) shows as CHANGED.
- Top-level hash (`entries_sha256`): sha256 of the JSON array of
  `{"bytes","path","sha256"}` objects sorted by path, keys sorted, separators
  `,` and `:`, UTF-8. `check` recomputes it and refuses a Base that does not
  match.
- The check accepts any Base manifest with a `files` list whose entries have
  `path` and `sha256`, and `bytes` or `size`.

## Running the tests

    python3 test_conformance.py -v

Some tests use symlinks, named pipes, or chmod. Those skip themselves on
platforms where they do not apply, and the unreadable-file test skips when
run as root.
