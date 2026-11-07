#!/usr/bin/env python3
"""fcl - FC-Link client for the Agape node-cluster command layer.

Speaks the live FC-Link wire protocol (fclink-1.3.x, legacy HMAC scheme):

  every request is signed, including GETs, with headers
    X-FC-TS          unix seconds when the request was made
    X-FC-Nonce       single-use random nonce, fresh per request
    X-FC-Body-SHA256 hex sha256 of the exact body bytes sent
    X-FC-Sig         hex HMAC-SHA256(key, "METHOD\\nPATH\\nTS\\nNONCE\\nBODY_SHA256")
  PATH includes the query string when one is present. Clock skew vs the
  node must stay within 300 s or the node rejects the request.

The key is the node's shared FC-Link key: raw bytes read from `keyfile`
(default ~/.config/fclink/key, mode 600 on-box). Keys live outside this
repo, always.

Client contract (kept identical to the call site in
gadgets/roach/satellite.py, which must keep working unmodified):

    FCLink(host, port=8765, keyfile="~/.config/fclink/key", timeout)
    .ls()  -> [{"name": ...}, ...]
    .get(name, dest_path) -> {"sha256": ..., "size": ...}
    .put(local_path, name)

Plus the cluster command verbs added by this module:

    .health()                  GET  /health
    .cmd(verb, **params)       POST /jobs   (job types below)
    .job(job_id)               GET  /jobs/<id>
    .wait_job(job_id)          poll .job() until a terminal state

Job verbs (see fclink_cmd.py for the server-side executor):
    "run"     {argv: [...]}                 allowlisted argv, no shell
    "read"    {path}                        result carries content_b64
    "sha256"  {path}                        (served by FC-Link 1.3.3 today)
    "verify"  {path, expect}                (served by FC-Link 1.3.3 today)
    "write"   {path, content_b64}           no-overwrite, roots-confined
  File *transfer* is not a job: use .put()/.get() (PUT/GET /files/<name>),
  which is how the live protocol serves writes.

Transport is a detail under this envelope: TCP 8765 over lab cable,
tailnet, or the Bluetooth PAN (192.168.79.x) all carry the same signed
requests. Phone is optional and never in the path.

Stdlib only.
"""

import hashlib
import hmac
import http.client
import json
import os
import secrets
import socket
import time
import urllib.parse

DEFAULT_PORT = 8765
DEFAULT_KEYFILE = "~/.config/fclink/key"
TERMINAL_JOB_STATES = ("ok", "rejected", "error", "done", "failed")


class FCLError(Exception):
    """A node answered with an error status (or the answer was unusable)."""

    def __init__(self, status, problem):
        self.status = status
        self.problem = problem
        super().__init__("FC-Link error %s: %s" % (status, problem))


def load_key(keyfile):
    """Read the shared key bytes from `keyfile`.

    The on-box convention is raw key bytes in a mode-600 file. A single
    trailing newline (an artifact of how the file was created) is not
    part of the key and is stripped.
    """
    path = os.path.expanduser(keyfile)
    with open(path, "rb") as fh:
        data = fh.read()
    if data.endswith(b"\r\n"):
        data = data[:-2]
    elif data.endswith(b"\n"):
        data = data[:-1]
    if not data:
        raise ValueError("empty FC-Link key file: %s" % path)
    return data


def body_sha256(body):
    return hashlib.sha256(body).hexdigest()


def request_mac(key, method, path, ts, nonce, body_hash):
    msg = "%s\n%s\n%s\n%s\n%s" % (method, path, ts, nonce, body_hash)
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_headers(key, method, path, body, ts=None, nonce=None):
    """Build the four X-FC-* auth headers for one request.

    `ts`/`nonce` are injectable so tests can craft stale or replayed
    requests; production callers leave both None (fresh values).
    """
    if ts is None:
        ts = int(time.time())
    if nonce is None:
        nonce = secrets.token_hex(16)
    bsha = body_sha256(body)
    return {
        "X-FC-TS": str(ts),
        "X-FC-Nonce": nonce,
        "X-FC-Body-SHA256": bsha,
        "X-FC-Sig": request_mac(key, method, path, ts, nonce, bsha),
    }


class FCLink:
    def __init__(self, host, port=DEFAULT_PORT, keyfile=DEFAULT_KEYFILE,
                 timeout=20):
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self.key = load_key(keyfile)

    # -- transport ----------------------------------------------------
    def _request(self, method, path, body=b"", extra_headers=None):
        headers = sign_headers(self.key, method, path, body)
        headers["X-FC-From"] = socket.gethostname()
        if extra_headers:
            headers.update(extra_headers)
        conn = http.client.HTTPConnection(self.host, self.port,
                                          timeout=self.timeout)
        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            resp_headers = {}
            for name, value in resp.getheaders():
                resp_headers[name.lower()] = value
            return resp.status, resp_headers, data
        finally:
            conn.close()

    def _json(self, method, path, obj=None):
        body = b""
        extra = None
        if obj is not None:
            body = json.dumps(obj, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")
            extra = {"Content-Type": "application/json"}
        status, _headers, data = self._request(method, path, body, extra)
        parsed = None
        if data:
            try:
                parsed = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                parsed = None
        if status >= 400:
            raise FCLError(status, parsed if parsed is not None
                           else data.decode("utf-8", "replace"))
        return parsed

    # -- file lane (live protocol: GET/PUT /files) ---------------------
    def ls(self):
        out = self._json("GET", "/files")
        if isinstance(out, list):
            return out
        if isinstance(out, dict):
            if isinstance(out.get("files"), list):
                return out["files"]
            merged = []
            for box in ("inbox", "outbox"):
                for entry in out.get(box) or []:
                    if isinstance(entry, dict):
                        entry = dict(entry)
                        entry.setdefault("box", box)
                        merged.append(entry)
            return merged
        return []

    def get(self, name, dest_path):
        path = "/files/" + urllib.parse.quote(name, safe="")
        status, headers, data = self._request("GET", path)
        if status >= 400:
            raise FCLError(status, data.decode("utf-8", "replace"))
        digest = hashlib.sha256(data).hexdigest()
        claimed = headers.get("x-fc-sha256")
        if claimed and claimed.lower() != digest:
            raise FCLError(status, "sha256 mismatch on get of %s: "
                           "node claimed %s, received %s"
                           % (name, claimed, digest))
        parent = os.path.dirname(os.path.abspath(dest_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(dest_path, "wb") as fh:
            fh.write(data)
        return {"sha256": digest, "size": len(data)}

    def put(self, local_path, name):
        with open(local_path, "rb") as fh:
            body = fh.read()
        path = "/files/" + urllib.parse.quote(name, safe="")
        status, _headers, data = self._request(
            "PUT", path, body, {"Content-Type": "application/octet-stream"})
        if status >= 400:
            parsed = None
            try:
                parsed = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                pass
            raise FCLError(status, parsed if parsed is not None
                           else data.decode("utf-8", "replace"))
        if data:
            try:
                return json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                pass
        return {"ok": True, "name": name,
                "sha256": hashlib.sha256(body).hexdigest(),
                "size": len(body)}

    # -- health ---------------------------------------------------------
    def health(self):
        return self._json("GET", "/health")

    # -- command lane (POST /jobs) --------------------------------------
    def cmd(self, verb, **params):
        """Submit one command job; returns the job record.

        Verbs: "run" (argv=[...]), "read" (path=...),
        "sha256" (path=...), "verify" (path=..., expect=...),
        "write" (path=..., content_b64=...).
        The record's "status" is terminal once it is one of
        TERMINAL_JOB_STATES; use .wait_job() to poll to completion.
        """
        job = {"type": verb}
        job.update(params)
        return self._json("POST", "/jobs", job)

    def job(self, job_id):
        return self._json("GET", "/jobs/" + urllib.parse.quote(str(job_id),
                                                               safe=""))

    def wait_job(self, job_id, timeout=30, interval=0.2):
        deadline = time.time() + timeout
        while True:
            rec = self.job(job_id)
            if isinstance(rec, dict) and \
                    rec.get("status") in TERMINAL_JOB_STATES:
                return rec
            if time.time() >= deadline:
                raise TimeoutError("job %s not terminal after %ss: %s"
                                   % (job_id, timeout, rec))
            time.sleep(interval)
