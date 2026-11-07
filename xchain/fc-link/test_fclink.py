#!/usr/bin/env python3
"""test_fclink - self-contained checks for the FC-Link command layer.

Plain asserts, no framework, no box paths. Builds a throwaway key and
temp file roots, starts the fclink_cmd reference adapter on an
ephemeral loopback port, and drives it with the real fcl.FCLink
client over the signed wire protocol.

Run:  python3 -B test_fclink.py     (exit 0 only if every check passes)
"""

import base64
import hashlib
import http.client
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fcl
import fclink_cmd

PASSED = []


def check(name, cond):
    assert cond, "CHECK FAILED: %s" % name
    PASSED.append(name)
    print("PASS: %s" % name)


def ledger_lines(path):
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def ledger_tail(path):
    rows = ledger_lines(path)
    return rows[-1] if rows else None


def run_cmd(client, verb, **params):
    rec = client.cmd(verb, **params)
    if rec.get("status") not in fcl.TERMINAL_JOB_STATES:
        rec = client.wait_job(rec["id"])
    return rec


def raw_request(port, method, path, headers, body=b""):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        resp.read()
        return resp.status
    finally:
        conn.close()


def main():
    work = tempfile.mkdtemp(prefix="fclink-test-")
    httpd = None
    try:
        inbox = os.path.join(work, "inbox")
        outbox = os.path.join(work, "outbox")
        elsewhere = os.path.join(work, "elsewhere")
        for d in (inbox, outbox, elsewhere):
            os.makedirs(d)

        # Throwaway key, temp dir only, never the repo.
        secret_path = os.path.join(work, "shared.bin")
        key_bytes = os.urandom(32)
        with open(secret_path, "wb") as fh:
            fh.write(key_bytes)
        os.chmod(secret_path, 0o600)

        ledger = os.path.join(work, "fclink-ctl.jsonl")
        httpd, node = fclink_cmd.serve("127.0.0.1", 0, key_bytes,
                                       "TESTNODE", [inbox, outbox],
                                       ledger)
        port = httpd.server_address[1]
        client = fcl.FCLink("127.0.0.1", port, secret_path, 10)

        # -- health -----------------------------------------------------
        health = client.health()
        check("health OK", health.get("ok") is True
              and health.get("host") == "TESTNODE")

        # -- run: allowlisted -------------------------------------------
        rec = run_cmd(client, "run", argv=["hostname"])
        check("run allowlisted (hostname) OK",
              rec["status"] == "ok" and rec["exit"] == 0
              and rec["result"]["stdout"].strip() != "")
        tail = ledger_tail(ledger)
        check("run OK ledgered",
              tail["verb"] == "run" and tail["result"] == "ok"
              and tail["node"] == "TESTNODE")

        # -- run: not allowlisted -----------------------------------------
        rec = run_cmd(client, "run", argv=["cat", "/etc/hostname"])
        check("run non-allowlisted (cat) REJECTED",
              rec["status"] == "rejected"
              and rec["result"]["reason"] == "command_not_allowlisted")
        tail = ledger_tail(ledger)
        check("rejection ledgered as rejected",
              tail["verb"] == "run" and tail["result"] == "rejected")

        # -- read: inside roots --------------------------------------------
        hello = os.path.join(inbox, "hello.txt")
        with open(hello, "w", encoding="utf-8") as fh:
            fh.write("hello cluster\n")
        rec = run_cmd(client, "read", path=hello)
        got = base64.b64decode(rec["result"]["content_b64"]) \
            if rec["status"] == "ok" else b""
        check("read inside roots OK", rec["status"] == "ok"
              and got == b"hello cluster\n")

        # -- read: outside roots --------------------------------------------
        outside = os.path.join(elsewhere, "secret.txt")
        with open(outside, "w", encoding="utf-8") as fh:
            fh.write("not for the cluster\n")
        rec = run_cmd(client, "read", path=outside)
        check("read outside roots REJECTED",
              rec["status"] == "rejected"
              and rec["result"]["reason"] == "path_outside_roots")

        # -- sha256 (1.3.3 parity verb) --------------------------------------
        rec = run_cmd(client, "sha256", path=hello)
        expect = hashlib.sha256(b"hello cluster\n").hexdigest()
        check("sha256 job OK", rec["status"] == "ok"
              and rec["result"]["sha256"] == expect)

        # -- write: new file OK, overwrite REJECTED ---------------------------
        target = os.path.join(inbox, "note.txt")
        payload = base64.b64encode(b"first write\n").decode("ascii")
        rec = run_cmd(client, "write", path=target, content_b64=payload)
        ok_write = rec["status"] == "ok" and os.path.exists(target)
        with open(target, "rb") as fh:
            ok_write = ok_write and fh.read() == b"first write\n"
        check("write new file OK", ok_write)
        rec = run_cmd(client, "write", path=target, content_b64=payload)
        check("write overwrite REJECTED",
              rec["status"] == "rejected"
              and rec["result"]["reason"] == "exists_no_overwrite")

        # -- file lane: put / ls / get round trip ------------------------------
        src = os.path.join(work, "payload.bin")
        blob = os.urandom(2048)
        with open(src, "wb") as fh:
            fh.write(blob)
        put_rec = client.put(src, "payload.bin")
        check("put OK", put_rec.get("sha256")
              == hashlib.sha256(blob).hexdigest())
        try:
            client.put(src, "payload.bin")
            check("put overwrite REJECTED (409)", False)
        except fcl.FCLError as exc:
            check("put overwrite REJECTED (409)", exc.status == 409)
        names = [entry["name"] for entry in client.ls()]
        check("ls lists transferred file", "payload.bin" in names)
        dest = os.path.join(work, "downloaded.bin")
        got_rec = client.get("payload.bin", dest)
        with open(dest, "rb") as fh:
            same = fh.read() == blob
        check("get round trip sha256 verified",
              same and got_rec["sha256"]
              == hashlib.sha256(blob).hexdigest())

        # -- auth: tampered signature -------------------------------------------
        hdrs = fcl.sign_headers(key_bytes, "GET", "/health", b"")
        sig = hdrs["X-FC-Sig"]
        hdrs["X-FC-Sig"] = sig[:-1] + ("0" if sig[-1] != "0" else "1")
        status = raw_request(port, "GET", "/health", hdrs)
        check("tampered signature REJECTED", status == 401)

        # -- auth: replayed nonce -------------------------------------------------
        hdrs = fcl.sign_headers(key_bytes, "GET", "/health", b"",
                                nonce="replay-test-nonce-0001")
        first = raw_request(port, "GET", "/health", hdrs)
        second = raw_request(port, "GET", "/health", hdrs)
        check("replayed nonce REJECTED", first == 200 and second == 401)

        # -- auth: stale timestamp --------------------------------------------------
        hdrs = fcl.sign_headers(key_bytes, "GET", "/health", b"",
                                ts=int(time.time()) - 10000)
        status = raw_request(port, "GET", "/health", hdrs)
        check("stale TS REJECTED", status == 401)

        # -- ledger integrity ---------------------------------------------------------
        ok, note = fclink_cmd.ledger_verify(ledger)
        check("ledger_verify PASS (%s)" % note, ok)

        bad = os.path.join(work, "fclink-ctl-tampered.jsonl")
        with open(ledger, "rb") as fh:
            data = bytearray(fh.read())
        idx = data.find(b"\n") + 5
        data[idx] = ord("X") if data[idx] != ord("X") else ord("Y")
        with open(bad, "wb") as fh:
            fh.write(bytes(data))
        ok, _note = fclink_cmd.ledger_verify(bad)
        check("ledger_verify FAIL on one flipped byte", not ok)

        print("ALL %d CHECKS PASS" % len(PASSED))
        return 0
    finally:
        if httpd is not None:
            httpd.shutdown()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
