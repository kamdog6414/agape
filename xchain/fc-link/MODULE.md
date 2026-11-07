# Agape module: fc-link cluster commands (FC-LINK CMD v0)

Musegadget-style messaging and command capabilities for node clusters,
built into FC-Link/xchain and running as a portion of Agape: any node
in a cluster can send a signed command to any other node - health,
run, read, write - and every command and its outcome lands in a
hash-chained audit ledger on the node that executed it.

Hosted computer-to-computer. The phone is optional and is never in
the path: the Muse gadget lane (BLE pairing, phone relay) is how a
human reaches one box; this layer is how the boxes reach each other.

Why it exists: FC-Link 1.3.3 already moves signed files and
sha256/verify jobs between nodes, but has no exec verb. This module is
that extension - a client (`fcl.py`) that keeps the existing FCLink
contract, and a server-side executor (`fclink_cmd.py`) a node operator
drops beside fclink.py.

Files:
  fcl.py          client: FCLink(host, port=8765, keyfile, timeout)
                  with .ls()/.get()/.put() (the satellite.py contract,
                  unchanged) plus .health()/.cmd()/.job()/.wait_job()
  fclink_cmd.py   server side: verify_request(), NonceCache,
                  Executor, ledger_verify(), and a loopback reference
                  HTTP adapter for demos/tests
  test_fclink.py  self-contained plain-assert checks (temp dirs only)

Commands:
  python3 -B test_fclink.py
  python3 -B fclink_cmd.py --bind 127.0.0.1 --port 8765 \
      --root ~/continuity/link/inbox --root ~/continuity/link/outbox \
      --ledger ~/continuity/link/fclink-ctl.jsonl        # demo only

Wire protocol (the live FC-Link 1.3.x legacy HMAC scheme, unchanged):
  Every request - GETs included - carries
    X-FC-TS, X-FC-Nonce, X-FC-Body-SHA256, X-FC-Sig
  with Sig = hex HMAC-SHA256(key,
    "METHOD\nPATH\nTS\nNONCE\nBODY_SHA256"), PATH including any query
  string. Timestamp skew must be <= 300 s; nonces are single-use.
  Key: the node's shared FC-Link key at ~/.config/fclink/key
  (raw bytes, mode 600 on-box). Keys live OUTSIDE this repo, always;
  nothing in this module ships, generates, or logs key material.

Verbs (POST /jobs, result polled via GET /jobs/<id>):
  health              GET /health - liveness (exists in 1.3.3 today)
  run     {argv}      execute an allowlisted argv, no shell
  read    {path}      file content from inside the node's roots,
                      returned base64 in the job result + its sha256
  sha256  {path}      file hash/size (exists in 1.3.3 today)
  verify  {path,expect}  hash compared against an expected value
  write   {path,content_b64}  create-only write inside the roots
  File transfer proper is NOT a job: use put()/get()
  (PUT/GET /files/<name>), the live protocol's own write/read lane.

Fail-closed rules (the executor grants nothing by default):
  - A request that fails signature, body-hash, timestamp, or nonce
    checks is rejected before anything executes - and the rejection
    itself is ledgered.
  - "run" executes only argv[0] basenames on the node's own
    COMMAND_ALLOWLIST (default: sha256sum, hostname, uptime, df - a
    read-only starter set). A node widens its list only through its
    own local config file; a request can never widen it.
  - File verbs resolve the real path and require it to sit inside the
    node's configured ROOTS (its fc-link inbox/outbox); symlinks
    cannot escape. "write" and PUT never overwrite (409-style
    refusal), mirroring the live protocol.
  - Every accepted AND rejected command appends one record to the
    node's fclink-ctl.jsonl: {ts, node, from, verb, params_sha256,
    result: ok|rejected|error, exit, prev, hash} - satellite canon
    (sort_keys, compact separators, hash over the whole body minus
    the hash field, prev-linked; ledger_verify() re-walks it).
    Command payloads never enter xchain.jsonl: its witness-record
    hash input is fixed (ts/self_head/peers/prev_hash) and is not
    forked by this module.

Transports: one envelope, any road. TCP 8765 over lab cable, tailnet,
or the Bluetooth PAN (192.168.79.x, the fclink-bt leg) - the transport
is a detail under the same signed requests. BLE provisioning (handing
a new node its WiFi/cluster config over Bluetooth) is the underlay
roadmap item for standing up fresh nodes with no network at all.

Status and the bar for shipping: v0 is the protocol core - client,
executor, ledger, and a tested loopback reference adapter. Production
wiring (Executor inside fclink.py's /jobs on each box) is on-box
follow-up work. The founder's ship criterion, set 2026-11-06: setup
must end simple enough to help grandma stand up her own node cluster.
v0 does not meet that bar yet and says so plainly - the one-command
installer and the guided first-cluster flow are the later work that
closes it.
