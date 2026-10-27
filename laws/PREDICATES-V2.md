Muse Wonder - LAWS-SEAT

# Agape Laws v2 - the named-point chain

Built on the founder's ruling on the L-11 question, 2026-10-26:
*L-11 checks each round's own named point and confirms the chain
leads back to this morning's point.*

## What changed from v1, and what did not

- **Changed:** `named_point_hash`. v1 hashed one fixed manifest
  and compared it to a constant pin. v2 hashes the manifest the
  round presents, then walks its parent links to genesis.
- **Unchanged:** genesis is the root of trust.
  `GENESIS_MANIFEST_SHA256 = e605b853...e7b7` (NP-20261026T170000Z)
  never moves, in any version. The three content predicates
  (`no_secrets_in_mod`, `no_network`, `black_and_white`) are
  v1's code, imported, not re-implemented.
- **Governance:** laws.py v1 is the Round 0 scorer of record and
  is not edited. laws_v2.py governs Round 1 and later.

## The chain contract (for whoever stamps a new point)

A point manifest is a `MANIFEST.json` in a folder of its own
(folder-per-point layout, as the genesis point already sits).
Its parent link is its **`supersedes.sha256`** field: the file
sha256 of the parent point's MANIFEST.json - the same field the
genesis manifest itself uses to name the baseline it replaced.
`parent_manifest_sha256` (top-level, 64-hex) is accepted as an
alias. A manifest with neither field can only pass if it IS
genesis (hash equals the pin).

Verification walks: hash presented file -> if pin, done (depth
0) -> else read parent link -> find that manifest by hash among
the points folders -> repeat. The walk fails on: unreadable
manifest, no parent link, parent manifest not found, a cycle,
or depth over 64. Failure is a FAIL verdict with a reason, never
an exception and never a guess.

## Interface (laws_v2.py)

- `verify_point(manifest_path, search_dirs=None)` ->
  `{point, manifest_sha256, chain, depth, verdict, reason}`.
  `chain` lists manifest sha256s from the presented point down
  to genesis; `depth` counts parent hops.
- `named_point_hash(manifest_path, search_dirs=None)` -> bool.
- `evaluate(mod_root, manifest_path, search_dirs=None)` -> the
  four predicate verdicts, same names and order as v1.
- `passed_names(...)` -> names for `core.note_laws(...)`.

Parent manifests are searched in: the presented manifest's
folder, its parent folder, that folder's immediate subfolders,
plus any `search_dirs`. Point the round tool at the round's own
manifest; the layout does the rest.

## Scorer (scorer_v2.py)

Same receipt shape as scorer.py, plus `point_verification`
(the full verify_point dict) in the receipt and the evidence
file. The named-point law's evidence cites the presented
manifest itself; the chain is in the receipt for any second
seat to re-walk.

## Scope, stated plainly

The chain proves each point was stamped standing on the last -
it makes quiet re-basing (a new point with no parent, or the
wrong one) a visible FAIL instead of an invisible rewrite.
It does not prove a point's *contents* are honest; that is what
the rest of the judging is for.
