# Atom baseline (description only)

The atom baseline is a frozen manifest (BASELINE-atom.json, pinned by its
sha256 prefix 321fe6a4) that records, for each witness chain, how many
records existed and the hash at that point. `xchain.py baseline --manifest M
--peers-dir D` then checks every peer chain against it:

- unchanged prefix + new appended records -> ok
- any edited record before the atom point -> "ATOM BROKEN (hash mismatch at N)"
- a chain shorter than the atom point -> "ATOM BROKEN (truncated ...)"
- the manifest itself edited (pin mismatch) -> "ATOM MANIFEST BROKEN"
- a chain that is missing -> "ATOM UNKNOWN" (not broken)

Tests: xchain/v1/test_baseline.sh (5 cases). The manifest itself is sealed
and is NOT included in this repository; only its pin prefix is.
