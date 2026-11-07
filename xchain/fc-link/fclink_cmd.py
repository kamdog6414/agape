#!/usr/bin/env python3
"""fclink_cmd - FC-Link cluster command executor (the piece 1.3.3 lacks).

FC-Link 1.3.3 serves health, file transfer, and sha256/verify jobs. It
has no exec verb. This module is the server-side extension a node
operator drops beside fclink.py to add gadget-style typed commands -
"run", "read", "write" - under the exact same wire discipline:

  * every request is HMAC-verified before anything executes
    (see verify_request; signature = HMAC-SHA256 over
    "METHOD\\nPATH\\nTS\\nNONCE\\nBODY_SHA256", constant-time compare,
    TS skew <= 300 s, nonces single-use);
  * execution is FAIL-CLOSED: "run" only runs argv[0] basenames on the
    node's own COMMAND_ALLOWLIST, never through a shell; file verbs
    only touch paths confined to the node's configured ROOTS; "write"
    never overwrites;
  * every accepted AND rejected command is appended to a hash-chained
    audit ledger, fclink-ctl.jsonl, in the satellite canon
    (json sort_keys, compact separators, hash = sha256 of the whole
    record body minus the hash field, prev-linked). Command payloads
    never enter xchain.jsonl - its witness-record hash input is fixed
    and must not be forked.

Contents:
  verify_request()  the auth gate (pure function, unit-testable)
  NonceCache        single-use nonce store (memory + optional file)
  Executor          allowlisted command execution + ctl ledger
  ledger_verify()   re-walk a ctl ledger and prove it intact
  make_handler()    a stdlib reference HTTP adapter (see below)

The reference adapter at the bottom exists so the layer can be demoed
and tested standalone on loopback. PRODUCTION integration - wiring
Executor.execute() into fclink.py's own /jobs handler on each box - is
on-box follow-up work, not part of this build.

Stdlib only.
"""

import base64
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import time

TS_SKEW_S = 300
NONCE_WINDOW_S = 600
MAX_PATH_BYTES = 8 * 1024 * 1024        # cap for "read" job results
MAX_OUTPUT_BYTES = 64 * 1024            # cap for "run" stdout/stderr
DEFAULT_RUN_TIMEOUT_S = 15

# The safe read-only starter set. A node opts in to more ONLY through
# its own config file (see Executor.from_config); nothing here can be
# widened by a request.
DEFAULT_COMMANDS = ("sha256sum", "hostname", "uptime", "df")

GENESIS = "GENESIS"


def canon(obj):
    """The satellite canon: one serialization for hashes and storage."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def sha256_hex(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def utc_ts():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def problem(status, code, detail):
    return {"status": status, "error": code, "detail": detail}


# ----------------------------------------------------------------------
# Auth gate
# ----------------------------------------------------------------------

class NonceCache:
    """Single-use nonces, bounded by a time window.

    In-memory set plus an optional append-only file so a restart does
    not reopen the replay window. Entries older than the window are
    pruned on each check.
    """

    def __init__(self, path=None, window=NONCE_WINDOW_S):
        self.path = path
        self.window = window
        self._seen = {}
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ts_s, nonce = line.split(" ", 1)
                            self._seen[nonce] = int(ts_s)
                        except ValueError:
                            continue
            except OSError:
                pass

    def check_and_add(self, nonce, ts, now=None):
        """True if `nonce` is fresh (and records it); False on replay."""
        if now is None:
            now = int(time.time())
        cutoff = now - self.window
        self._seen = {n: t for n, t in self._seen.items() if t >= cutoff}
        if nonce in self._seen:
            return False
        self._seen[nonce] = ts
        if self.path:
            try:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write("%d %s\n" % (ts, nonce))
            except OSError:
                pass
        return True


def verify_request(method, path, headers, body, key, nonces, now=None):
    """Verify one signed FC-Link request.

    `headers` is any mapping; names are matched case-insensitively.
    Returns (True, None) on success, (False, problem_dict) on any
    failure. Every failure is a rejection - there is no partial pass.
    The nonce is consumed only after the signature verifies, so a
    forged request cannot burn a victim's nonce.
    """
    if now is None:
        now = int(time.time())
    hdrs = {}
    for name, value in headers.items():
        hdrs[name.lower()] = value
    ts_raw = hdrs.get("x-fc-ts")
    nonce = hdrs.get("x-fc-nonce")
    body_hash = hdrs.get("x-fc-body-sha256")
    sig = hdrs.get("x-fc-sig")
    if not ts_raw or not nonce or not body_hash or not sig:
        return False, problem(401, "missing_auth_headers",
                              "X-FC-TS, X-FC-Nonce, X-FC-Body-SHA256 and "
                              "X-FC-Sig are all required")
    actual_body_hash = sha256_hex(body)
    if not hmac.compare_digest(actual_body_hash, body_hash.lower()):
        return False, problem(401, "body_hash_mismatch",
                              "X-FC-Body-SHA256 does not match the body")
    try:
        ts = int(ts_raw)
    except (TypeError, ValueError):
        return False, problem(401, "bad_ts", "X-FC-TS is not an integer")
    if abs(now - ts) > TS_SKEW_S:
        return False, problem(401, "stale_ts",
                              "timestamp outside the +/-%ds window"
                              % TS_SKEW_S)
    msg = "%s\n%s\n%s\n%s\n%s" % (method, path, ts_raw, nonce, body_hash)
    expected = hmac.new(key, msg.encode("utf-8"),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig.lower()):
        return False, problem(401, "bad_signature",
                              "HMAC-SHA256 signature does not verify")
    if not nonces.check_and_add(nonce, ts, now):
        return False, problem(401, "nonce_replay",
                              "nonce has already been used")
    return True, None


# ----------------------------------------------------------------------
# Command/result ledger (satellite canon, prev-linked)
# ----------------------------------------------------------------------

def ledger_tail_hash(path):
    if not path or not os.path.exists(path):
        return GENESIS
    last = GENESIS
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    last = json.loads(line)["hash"]
                except (ValueError, KeyError):
                    continue
    return last


def ledger_append(path, node, frm, verb, params, result, exit_code):
    """Append one command record; returns the record written."""
    rec = {
        "ts": utc_ts(),
        "node": node,
        "from": frm,
        "verb": verb,
        "params_sha256": sha256_hex(canon(params)),
        "result": result,
        "exit": exit_code,
        "prev": ledger_tail_hash(path),
    }
    rec["hash"] = sha256_hex(canon(rec))
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(canon(rec) + "\n")
    return rec


def ledger_verify(path):
    """Re-walk a ctl ledger. Returns (True, note) or (False, reason)."""
    if not os.path.exists(path):
        return False, "ledger missing: %s" % path
    prev = GENESIS
    count = 0
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                return False, "line %d: not JSON" % lineno
            if rec.get("prev") != prev:
                return False, "line %d: prev link broken" % lineno
            claimed = rec.get("hash")
            body = {k: v for k, v in rec.items() if k != "hash"}
            if not claimed or sha256_hex(canon(body)) != claimed:
                return False, "line %d: hash mismatch" % lineno
            prev = claimed
            count += 1
    return True, "OK: %d records, head %s" % (count, prev[:16])


# ----------------------------------------------------------------------
# Executor
# ----------------------------------------------------------------------

class Executor:
    """Fail-closed execution of FC-Link command jobs on one node.

    roots:    directories the file verbs may touch (the node's fc-link
              inbox/outbox by default). Paths are realpath-resolved and
              must land inside a root; symlinks cannot escape.
    commands: allowlisted argv[0] basenames for "run".
    ledger:   path of this node's fclink-ctl.jsonl.
    """

    def __init__(self, node, roots, ledger_path, commands=None,
                 run_timeout=DEFAULT_RUN_TIMEOUT_S):
        self.node = node
        self.roots = [os.path.realpath(os.path.expanduser(r))
                      for r in roots]
        self.ledger_path = ledger_path
        self.commands = set(commands) if commands is not None \
            else set(DEFAULT_COMMANDS)
        self.run_timeout = run_timeout

    @classmethod
    def from_config(cls, node, config_path, roots, ledger_path):
        """Node-local opt-in: widen the allowlist from the node's OWN
        config file ({"commands": [...]}). Requests can never do this."""
        commands = set(DEFAULT_COMMANDS)
        if config_path and os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            for name in cfg.get("commands") or []:
                commands.add(os.path.basename(str(name)))
            if cfg.get("roots"):
                roots = [str(r) for r in cfg["roots"]]
        return cls(node, roots, ledger_path, commands)

    # -- confinement ----------------------------------------------------
    def confine(self, path):
        """Realpath of `path` if it sits inside a root, else None."""
        if not path or not isinstance(path, str):
            return None
        rp = os.path.realpath(os.path.expanduser(path))
        for root in self.roots:
            if rp == root or rp.startswith(root + os.sep):
                return rp
        return None

    # -- main entry -------------------------------------------------------
    def execute(self, job, frm="?"):
        """Execute one job dict; ALWAYS appends a ctl ledger record.

        Returns the job record {id, type, status, exit, result} where
        status is "ok", "rejected" or "error" (all terminal).
        """
        if not isinstance(job, dict):
            job = {}
        verb = job.get("type") or job.get("verb") or "unknown"
        params = {k: v for k, v in job.items()
                  if k not in ("type", "verb")}
        handler = {
            "run": self._run,
            "read": self._read,
            "sha256": self._sha256,
            "verify": self._verify,
            "write": self._write,
        }.get(verb)
        if handler is None:
            status, exit_code, data = "rejected", None, \
                {"reason": "unknown_verb", "verb": verb}
        else:
            status, exit_code, data = handler(params)
        ledger_append(self.ledger_path, self.node, frm, verb, params,
                      status, exit_code)
        return {"id": job.get("id"), "type": verb, "status": status,
                "exit": exit_code, "result": data}

    def note_rejection(self, frm, verb, params, reason):
        """Ledger an attempt that never reached execute() (bad auth,
        malformed body) so the audit chain sees rejections too."""
        ledger_append(self.ledger_path, self.node, frm, verb, params,
                      "rejected", None)
        return {"reason": reason}

    # -- verbs ------------------------------------------------------------
    def _run(self, params):
        argv = params.get("argv")
        if not isinstance(argv, list) or not argv or \
                not all(isinstance(a, str) for a in argv):
            return "rejected", None, {"reason": "argv_must_be_string_list"}
        base = os.path.basename(argv[0])
        if base not in self.commands:
            return "rejected", None, {"reason": "command_not_allowlisted",
                                      "command": base}
        exe = shutil.which(base)
        if exe is None:
            return "error", None, {"reason": "command_not_found",
                                   "command": base}
        if argv[0] != base and \
                os.path.realpath(argv[0]) != os.path.realpath(exe):
            return "rejected", None, {"reason": "argv0_path_mismatch",
                                      "command": base}
        try:
            proc = subprocess.run([exe] + argv[1:], shell=False,
                                  capture_output=True,
                                  timeout=self.run_timeout)
        except subprocess.TimeoutExpired:
            return "error", None, {"reason": "timeout",
                                   "command": base}
        out = proc.stdout.decode("utf-8", "replace")[:MAX_OUTPUT_BYTES]
        err = proc.stderr.decode("utf-8", "replace")[:MAX_OUTPUT_BYTES]
        status = "ok" if proc.returncode == 0 else "error"
        return status, proc.returncode, {"command": base,
                                         "stdout": out, "stderr": err}

    def _confined_file(self, params):
        rp = self.confine(params.get("path"))
        if rp is None:
            return None, ("rejected", None,
                          {"reason": "path_outside_roots",
                           "path": params.get("path")})
        if not os.path.isfile(rp):
            return None, ("error", None, {"reason": "not_a_file",
                                          "path": params.get("path")})
        return rp, None

    def _read(self, params):
        rp, fail = self._confined_file(params)
        if fail:
            return fail
        size = os.path.getsize(rp)
        if size > MAX_PATH_BYTES:
            return "error", None, {"reason": "file_too_large",
                                   "size": size}
        with open(rp, "rb") as fh:
            data = fh.read()
        return "ok", 0, {"path": params.get("path"), "size": len(data),
                         "sha256": sha256_hex(data),
                         "content_b64": base64.b64encode(
                             data).decode("ascii")}

    def _hash_file(self, rp):
        digest = hashlib.sha256()
        size = 0
        with open(rp, "rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size

    def _sha256(self, params):
        rp, fail = self._confined_file(params)
        if fail:
            return fail
        digest, size = self._hash_file(rp)
        return "ok", 0, {"path": params.get("path"), "sha256": digest,
                         "size": size}

    def _verify(self, params):
        rp, fail = self._confined_file(params)
        if fail:
            return fail
        digest, size = self._hash_file(rp)
        expect = params.get("expect")
        match = bool(expect) and digest == str(expect).lower()
        return ("ok" if match else "error"), (0 if match else 1), \
            {"path": params.get("path"), "sha256": digest, "size": size,
             "expect": expect, "match": match}

    def _write(self, params):
        rp = self.confine(params.get("path"))
        if rp is None:
            return "rejected", None, {"reason": "path_outside_roots",
                                      "path": params.get("path")}
        if os.path.exists(rp):
            return "rejected", None, {"reason": "exists_no_overwrite",
                                      "path": params.get("path")}
        b64 = params.get("content_b64")
        if not isinstance(b64, str):
            return "rejected", None, {"reason": "content_b64_required"}
        try:
            data = base64.b64decode(b64.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError):
            return "rejected", None, {"reason": "content_b64_invalid"}
        parent = os.path.dirname(rp)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(rp, "wb") as fh:
            fh.write(data)
        return "ok", 0, {"path": params.get("path"), "size": len(data),
                         "sha256": sha256_hex(data)}


# ----------------------------------------------------------------------
# Reference HTTP adapter.
#
# DEMO/TEST ONLY: this adapter exists so the command layer can be run
# and tested standalone on loopback. The production path is wiring
# Executor into fclink.py's own /jobs handler on each box (on-box
# follow-up work). Do not expose this adapter off-loopback as-is.
# ----------------------------------------------------------------------

import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ADAPTER_VERSION = "fclink-cmd-ref-0.1"


class Node:
    """One node's adapter state: key, nonce cache, executor, jobs."""

    def __init__(self, name, key, executor, nonce_path=None):
        self.name = name
        self.key = key
        self.executor = executor
        self.nonces = NonceCache(nonce_path)
        self.jobs = {}
        self.started = time.time()
        self._seq = 0
        self._lock = threading.Lock()

    def next_job_id(self):
        with self._lock:
            self._seq += 1
            return "job-%d-%d" % (int(time.time()), self._seq)

    def find_file(self, name):
        """Locate a transferable file by basename inside the roots."""
        base = os.path.basename(name)
        if base != name:
            return None
        for root in self.executor.roots:
            cand = os.path.join(root, base)
            if os.path.isfile(cand):
                return cand
        return None

    def list_files(self):
        out = []
        seen = set()
        for root in self.executor.roots:
            if not os.path.isdir(root):
                continue
            for entry in sorted(os.listdir(root)):
                full = os.path.join(root, entry)
                if entry in seen or not os.path.isfile(full):
                    continue
                seen.add(entry)
                digest, size = self.executor._hash_file(full)
                out.append({"name": entry, "size": size,
                            "sha256": digest})
        return out


def make_handler(node):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "FCLinkCmdRef/0.1"

        # -- plumbing -------------------------------------------------
        def log_message(self, *args):
            pass

        def _send(self, status, body, ctype="application/json",
                  extra=None):
            if isinstance(body, (dict, list)):
                body = canon(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("FC-Link-Version", "1.3")
            for name, value in (extra or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if body:
                self.wfile.write(body)
            self.close_connection = True

        def _read_body(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            return self.rfile.read(length) if length > 0 else b""

        def _from(self):
            return self.headers.get("X-FC-From") or \
                self.client_address[0]

        def _auth(self, body):
            ok, prob = verify_request(self.command, self.path,
                                      self.headers, body, node.key,
                                      node.nonces)
            if not ok and self.command == "POST" and \
                    self.path == "/jobs":
                verb, params = "unknown", {}
                try:
                    parsed = json.loads(body.decode("utf-8"))
                    if isinstance(parsed, dict):
                        verb = parsed.get("type") or "unknown"
                        params = {k: v for k, v in parsed.items()
                                  if k != "type"}
                except (ValueError, UnicodeDecodeError):
                    params = {"raw_body_sha256": sha256_hex(body)}
                node.executor.note_rejection(self._from(), verb, params,
                                             prob["error"])
            return ok, prob

        def _route_parts(self):
            path = urllib.parse.urlsplit(self.path).path
            return [p for p in path.split("/") if p != ""]

        # -- verbs ------------------------------------------------------
        def do_GET(self):
            body = self._read_body()
            ok, prob = self._auth(body)
            if not ok:
                return self._send(prob["status"], prob)
            parts = self._route_parts()
            if parts == ["health"]:
                return self._send(200, {
                    "ok": True, "version": ADAPTER_VERSION,
                    "host": node.name, "time": utc_ts(),
                    "uptime_s": int(time.time() - node.started),
                    "protocols": ["fclink-1.2", "fclink-1.3"]})
            if parts == ["files"]:
                return self._send(200, {"files": node.list_files()})
            if len(parts) == 2 and parts[0] == "files":
                name = urllib.parse.unquote(parts[1])
                full = node.find_file(name)
                if full is None:
                    return self._send(404, problem(
                        404, "not_found", "no such file: %s" % name))
                with open(full, "rb") as fh:
                    data = fh.read()
                return self._send(200, data,
                                  "application/octet-stream",
                                  {"X-FC-SHA256": sha256_hex(data)})
            if parts == ["jobs"]:
                return self._send(200,
                                  {"jobs": list(node.jobs.values())})
            if len(parts) == 2 and parts[0] == "jobs":
                rec = node.jobs.get(urllib.parse.unquote(parts[1]))
                if rec is None:
                    return self._send(404, problem(
                        404, "not_found", "no such job"))
                return self._send(200, rec)
            return self._send(404, problem(404, "not_found", self.path))

        def do_PUT(self):
            body = self._read_body()
            ok, prob = self._auth(body)
            if not ok:
                return self._send(prob["status"], prob)
            parts = self._route_parts()
            if len(parts) == 2 and parts[0] == "files":
                name = os.path.basename(urllib.parse.unquote(parts[1]))
                if not node.executor.roots:
                    return self._send(500, problem(
                        500, "no_roots", "node has no file roots"))
                target = os.path.join(node.executor.roots[0], name)
                if os.path.exists(target):
                    return self._send(409, problem(
                        409, "exists_no_overwrite",
                        "file already exists: %s" % name))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as fh:
                    fh.write(body)
                return self._send(201, {"ok": True, "name": name,
                                        "sha256": sha256_hex(body),
                                        "size": len(body)})
            return self._send(404, problem(404, "not_found", self.path))

        def do_POST(self):
            body = self._read_body()
            ok, prob = self._auth(body)
            if not ok:
                return self._send(prob["status"], prob)
            parts = self._route_parts()
            if parts == ["heartbeat"]:
                beats = os.path.join(
                    os.path.dirname(os.path.abspath(
                        node.executor.ledger_path)), "beats.jsonl")
                try:
                    with open(beats, "a", encoding="utf-8") as fh:
                        fh.write(canon({
                            "ts": utc_ts(), "from": self._from(),
                            "body_sha256": sha256_hex(body)}) + "\n")
                except OSError:
                    pass
                return self._send(200, {"ok": True, "time": utc_ts()})
            if parts == ["jobs"]:
                try:
                    job = json.loads(body.decode("utf-8"))
                    if not isinstance(job, dict):
                        raise ValueError("job must be an object")
                except (ValueError, UnicodeDecodeError):
                    node.executor.note_rejection(self._from(), "unknown",
                                                 {"raw_body_sha256":
                                                  sha256_hex(body)},
                                                 "malformed_job")
                    return self._send(400, problem(
                        400, "malformed_job", "body must be a JSON "
                        "object"))
                job["id"] = node.next_job_id()
                rec = node.executor.execute(job, self._from())
                node.jobs[rec["id"]] = rec
                return self._send(202, rec)
            return self._send(404, problem(404, "not_found", self.path))

    return Handler


def serve(host, port, key, node_name, roots, ledger_path, commands=None,
          nonce_path=None, config_path=None):
    """Start the reference adapter; returns (httpd, node).

    port=0 picks an ephemeral loopback port (what the tests use).
    """
    if config_path:
        executor = Executor.from_config(node_name, config_path, roots,
                                        ledger_path)
    else:
        executor = Executor(node_name, roots, ledger_path, commands)
    node = Node(node_name, key, executor, nonce_path)
    httpd = ThreadingHTTPServer((host, port), make_handler(node))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, node


if __name__ == "__main__":
    import argparse
    import socket
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from fcl import load_key

    ap = argparse.ArgumentParser(
        description="FC-Link command layer reference adapter "
                    "(loopback demo only)")
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--keyfile", default="~/.config/fclink/key")
    ap.add_argument("--root", action="append", required=True,
                    help="allowed file root (repeatable)")
    ap.add_argument("--ledger", default="fclink-ctl.jsonl")
    ap.add_argument("--config", default=None,
                    help="node-local allowlist opt-in config JSON")
    args = ap.parse_args()
    if args.bind not in ("127.0.0.1", "::1", "localhost"):
        ap.error("reference adapter binds loopback only; production "
                 "integration belongs inside fclink.py on the box")
    httpd, node = serve(args.bind, args.port, load_key(args.keyfile),
                        socket.gethostname(), args.root, args.ledger,
                        config_path=args.config)
    print("fclink-cmd reference adapter on %s:%d (node %s)"
          % (args.bind, args.port, node.name))
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        httpd.shutdown()
