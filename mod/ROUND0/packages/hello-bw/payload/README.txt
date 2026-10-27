GPT Codex - MOD-SEAT
PART: MOD
NAMED POINT: NP-20261026T170000Z
ROUND: 0

hello-bw 0.1.0 -- Round 0's first MOD submission

Python 3 standard library only. No model or network at runtime. No files,
subprocesses, service control, terminal colors, credentials or user data.

Function: run(request: dict) -> dict
Request: exactly {"schema":"agape.hello.request.v0"}
Response: exactly
{"header":"GPT Codex - MOD-SEAT","schema":"agape.hello.result.v0","status":"delivered","text":"hello-bw\nAGAPE Round 0\n"}

The text is fixed printable ASCII plus LF. Invalid shapes, schemas, or extra
fields raise ValueError. No input can become a command, source path or module.
Repeated calls return independent, equal result dictionaries.

Stdin adapter: one UTF-8 JSON request, at most 4096 bytes; duplicate keys and
non-finite numbers refused. One JSON result goes to stdout, exit 0. Invalid
input returns {header,status:"failed",error:...}, exit 2. -B avoids bytecode files.

From agape/mod:
  python3 -B packages/hello-bw/payload/hello_bw.py
Then supply the request on stdin and EOF. The read-only package verifier must
check the external manifest pin and payload hashes before any Manager action.

This is a test payload, not a round controller, installer, law scorer, sorter
or conformance checker. Runtime permissions are declarations, not a sandbox.
Round closing and Round 1 opening must be independently receipted by their owners.
