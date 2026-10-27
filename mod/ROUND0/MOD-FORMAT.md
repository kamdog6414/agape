GPT Codex - MOD-SEAT

# Agape MOD package format v0

PART: MOD
STATUS: delivered
NAMED POINT: NP-20261026T170000Z
UTC: 2026-10-26T17:39:50.590929Z
OWNER: GPT Codex - MOD-SEAT
NEED: N-004 (package format for Manager)

This is the published `agape.mod.v0` contract. It builds against the verified
`agape.base.v0` interface, whose Mod slot accepts an id and a manifest SHA256.
Manager owns installation, enabling and disabling. Sorter owns dependency order
and conflict decisions. Laws owns predicates. This package format does not
implement those parts or grant execution authority.

## Folder layout

```
<package-folder>/
  MANIFEST.json
  payload/
    recall.py
    README.txt
```

The name of the outer folder is immaterial. `MANIFEST.json` and exactly its
listed payload files constitute one package. No archive, executable installer,
lockfile, cache, hidden file, pin file, or unlisted file belongs inside it.
Receipts and the external manifest pin stay outside the package folder.
Directories must be ancestors of a listed payload file; empty extras are refused.

## Manifest fields (all required, no other keys in v0)

`MANIFEST.json` is UTF-8 JSON, no BOM, object at the root, no repeated object keys,
no NaN/Infinity. It is at most 65,536 bytes. The following is a field description,
not an installable manifest (file sizes and hashes must describe real bytes):

| Field | Type and exact meaning |
| --- | --- |
| header | nonempty author/seat string, at most 120 characters; attribution, not authentication |
| schema | literal `agape.mod.v0` |
| mod_id | stable lowercase id matching `[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*`, at most 80 characters |
| version | three decimal components `major.minor.patch`, no leading zero except `0`, at most 80 characters |
| named_point | literal `NP-20261026T170000Z` |
| created_utc | UTC timestamp `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` (1..6 optional fractional digits), strictly after `2026-10-26T17:00:00.381572Z`; it is a declared time, not cryptographic proof |
| base | object with exactly `version`, `interface_sha256`, `manifest_sha256`; see pins below |
| entrypoint | object with exactly `path`, `callable`, `protocol`; path is one listed `.py` file, callable is `run`, protocol is `agape.mod.call.v0` |
| runtime | exactly `{"language":"python3","dependencies":"stdlib","network":false,"filesystem":"none","processes":false}` for this v0 profile |
| inputs | nonempty array of distinct schema identifiers using the same id syntax, at most 16 |
| outputs | nonempty array of distinct schema identifiers using the same id syntax, at most 16 |
| requires | array of distinct other mod ids, sorted lexically, at most 64; empty means none; no self-reference |
| conflicts | array of distinct other mod ids, sorted lexically, at most 64; empty means none; no self-reference |
| files | nonempty array sorted by ASCII path, at most 64 entries; each entry has exactly `path`, `bytes`, `sha256` |

`bytes` is an integer (not Boolean) in 0..1,048,576. Payload bytes total at most
8,388,608. Every `sha256` is exactly 64 lowercase hexadecimal characters.
Each path begins `payload/`, uses `/`, and is at most 240 ASCII characters.
Each component matches `[A-Za-z0-9][A-Za-z0-9._-]{0,79}`; `.` and `..`, absolute
paths, backslashes, drive letters, trailing dots, Windows reserved device names,
and case-insensitive collisions (including directory components) are refused.
Credential filenames/extensions are refused before opening their bytes. The
case-insensitive rule rejects exact `id_rsa`/`id_ed25519`, extensions `.pem`,
`.key`, `.p12`, `.pfx`, and components containing a dot/underscore/hyphen-delimited
word in `key keys token tokens secret secrets auth authentication credential
credentials password passwords`. Hidden names such as `.env` are already refused
by the component rule. This name filter is not a claim that contents are secret-free;
Laws and human review retain that responsibility.
Links, reparse points, hardlinks, special files, cross-device nested filesystems
and more than 256 filesystem entries are refused. Same-device bind mounts are
not detected. The package root itself must be an ordinary
directory, not a link. Verify an immutable staging copy; concurrent hostile
filesystem mutation is outside this v0 verifier's guarantee.

### Base pins

```
version: agape.base.v0
interface_sha256: a40e530a26d92b749c7f79c54eb1b4cd7bce04f7942e9a303733a1e402e6b9b0
manifest_sha256: 10ba805c736495ede2469da1308590f6500ef62427145d5d64f252b64b6a2c37
named-point manifest: e605b853d6eea415073da043a65d9f28fb8b715e669d4ece94b0c74bee88e7b7
```

Future Base versions or extended runtime profiles require a new package contract;
this v0 reader refuses them. `requires` and `conflicts` are declarations for
Sorter; reading them is not a determination that a load order is valid.

## SHA256, without a circular hash

1. Hash every payload file's exact raw bytes; record its size and lowercase hash
   in `files`. Do not normalize newlines or decode/re-encode payloads.
2. Write the manifest once. Producer convention: `json.dumps(manifest,
   ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n"` as UTF-8.
3. Compute `manifest_sha256 = sha256(MANIFEST.json raw bytes).hexdigest()`.
   This is the package identity supplied to Base. **Do not canonicalize the JSON
   when verifying the pin.** Whitespace changes change identity.
4. Keep that pin in an external receipt/board post. Neither the manifest nor a
   pin file appears in the payload inventory. A trusted external pin is required;
   a package cannot establish its own provenance by rehashing itself.
5. Verify the external pin, strict manifest, exact inventory, and each payload's
   size/hash before Manager uses `core.enable(manifest["mod_id"], manifest_sha256)`.
   A mismatch refuses the package. Hash equality detects changed bytes; it does
   not authenticate an author or establish that executable code is safe.

## Reader and Manager handoff

MOD supplies `package.py` with:

```
verify_package(package_dir, expected_sha256) -> dict
```

It raises `PackageError` on malformed metadata, a pin mismatch, unsafe inventory,
or changed payload. The returned dict contains `mod_id`, `version`,
`manifest_sha256`, `entrypoint`, `requires`, `conflicts`, `file_count`, and
`payload_bytes`. The mandatory external pin is over raw `MANIFEST.json` bytes.

Command: `python3 -B package.py verify PACKAGE --sha256 EXTERNAL_PIN`.
Verification is read-only and never imports, executes, installs, enables,
disables, or reorders package code. Manager may consume this reader or implement
an equivalent reader against this published contract. MOD's tests alone use
Base's public calls in a disposable, in-memory core; they do not create a Manager.

## Offline execution protocol and first mod

`agape.mod.call.v0`: the Python entrypoint exposes `run(request: dict) -> dict`.
Under Work Order 3, Round 0's first submission is `hello-bw`, version `0.1.0`:
it consumes `agape.hello.request.v0` and emits `agape.hello.result.v0`, with fixed
ASCII text `hello-bw\nAGAPE Round 0\n`. Its payload README defines the exact
request and result. `round_id` belongs in the submission/round receipt, not as
an unrecognized field in the strict v0 package manifest. The package schema,
hash rule and fields are unchanged by this additional sample.

The earlier candidate `agape.source-recall`, version `0.1.0`, consumes
`agape.recall.request.v0` and emits `agape.recall.result.v0`. Its separate stdin/
stdout adapter accepts one UTF-8 JSON request and prints one JSON result, using
no network, filesystem paths, subprocesses or model. Inputs are caller-supplied
text plus source labels, not instructions or paths to open. Results quote exact
source lines with 1-based line numbers and the SHA256 of the original text's
UTF-8 bytes, or return `UNKNOWN` when no literal query supports an answer.
The exact request/result shapes are documented with the mod. The runtime fields
are declarations backed by first-mod source review and offline tests, not a
sandbox for arbitrary Python. No generic execution engine is included.

## Acceptance evidence

This document publishes the format before implementation. It does not claim
that a package reader, mod, Manager integration, offline test, or full Base
conformance has already passed. Those claims require separate timed receipts.
All work from before the named point remains pre-existing; it is not claimed
as development in this window.
