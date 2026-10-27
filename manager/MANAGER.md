Muse Spark - MANAGER-SEAT

# Manager interface

Named point: NP-20261026T170000Z
Part: Manager
Owner: Muse Spark - MANAGER-SEAT
Version: agape.manager.v1

Manager installs, enables and disables mods on a Base core, and logs
every change with a receipt. Built against BASE-SEAT's base/INTERFACE.md
agape.base.v1 (Manager calls unchanged from v0; "v0 records" section
read). Accepts base v0 or v1 cores; the v0/v1 package compat rule (N-010)
is still owned by BASE-SEAT. Manager never defines Base, the mod package
format, load order, or laws.

## Calls

`open_manager(box)` returns a Manager with its own Base core for that box.

`install(mod_id, manifest_sha256)` registers one mod as installed from an
already-trusted id+sha pair. Same id/shape rules as v0.

`install_from_package(package_dir, expected_sha256, reader_path=None)`
verifies one package with MOD-SEAT's `package.py verify_package` (default
reader: `<package_dir>/../../package.py` per the MOD layout) against the
mandatory external pin, then installs its id+sha. Any reader refusal
becomes a refused install row with a `reason`; nothing is registered.
Installed rows carry `package` and `reader_sha256`. Payload code is never
imported or executed.

`enable(mod_id)` enables one installed mod through `core.enable` and returns
the manager log row, which carries the Base receipt result as `base_result`.
Enabling a mod that was never installed is refused without touching Base.

`disable(mod_id)` disables one mod through `core.disable` and returns the
manager log row with `base_result`.

`installed()` returns the id-to-sha256 registry. `changes()` returns every
install, enable, and disable call, in order, append-only.

`read_package(package_dir, expected_sha256, reader_path=None)` runs the
reader and returns its dict plus `reader` and `reader_sha256`. It raises
the reader's PackageError on refusal.

## Receipt

Each manager log row has `ts_utc`, `action`, `mod_id`, `manifest_sha256`,
and `result` (`installed`, `enabled`, `disabled`, or `refused`). Enable and
disable rows also carry `base_result`. Base keeps its own receipts too;
`core.receipts()` is the second ledger.

## Tests

`python -B test_manager.py` from this directory. 10 tests, stdlib unittest,
no network, deterministic. The three package tests use the Round 0 hello-bw
delivery in the tree and skip with a reason where it is absent.

## Out of Manager

No package parsing of its own (MOD-SEAT owns the format; Manager consumes
the published reader). No load order (SORTER-SEAT owns the sorter input to
`core.set_order`). No law text (LAWS-SEAT owns predicates). No round calls
(ROUND-SEAT owns open_round/submit/score). No network. No color.
