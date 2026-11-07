# FC-Link over Bluetooth — the Agape underlay

Bluetooth is a first-class FC-Link transport in Agape, in two distinct
roles. The phone is optional in both: every flow runs node-to-node,
hosted computer to computer.

- **Provisioning** — a fresh node gets its WiFi credentials, FC-Link
  key, and cluster identity over BLE. No keyboard, no screen.
- **Transport** — the same signed FC-Link envelopes ride Bluetooth
  when no other network exists. The receipt discipline is identical
  on every transport; transport is a detail under the envelope.

Reference implementation: `ble_provision.py` (protocol core, hardware-
free, stdlib only) + `test_ble_provision.py`. The on-box BlueZ GATT
server is a later build that follows the profile pinned in that file.

## Role 1 — Transport: what already runs today

Bluetooth PAN (PANU/BNEP) gives the cluster an IP link with no
router, no cable, and no tailnet. This is live, not proposed:

- Nikolai binds FC-Link (TCP 8765) on `192.168.79.1` — the Bluetooth
  PAN address, /24 — alongside the lab cable (`192.168.77.1`) and the
  tailnet address. `fclink-bt.service` keeps the PAN link to SOV up;
  the server uses IP_FREEBIND so the address is held even while the
  PAN is down, and traffic flows the moment it returns.
- The signed HTTP envelopes from `fcl.py` (HMAC-SHA256, TS + nonce,
  body hash) are byte-identical on all three transports. Nothing
  about FC-Link changes when the medium is Bluetooth.

**Direct-GATT fallback (no IP at all).** If a node has Bluetooth but
no PAN — a new board, a minimal install — command envelopes can ride
GATT directly: the exact signed request bytes are chunked by
`ble_provision.chunk_payload()` and written to the chunk-rx
characteristic; the peer reassembles, verifies the whole-payload
sha256, and only then hands the bytes to the same request handler.
Same envelope, same signatures, same ledgering in `fclink_cmd.py`.
This path suits command traffic (health, run, read, small writes);
it is a fallback, not a bulk lane.

## Role 2 — Provisioning over BLE

Packet (JSON, canonical form for signing):

```
{v, node_name, ssid, psk, fclink_key_b64,
 cluster: {nodes: {name: host, ...}}, ts, nonce, sig}
```

`sig` is HMAC-SHA256 over the packet without `sig`, keyed with the
cluster FC-Link key — the same key the packet delivers
(`fclink_key_b64`). Verification is constant-time; TS skew ≤ 300 s;
nonces are single-use (caller-kept seen-set).

Transfer: the serialized packet is split into frames of ≤ 256 bytes
(the boxes' BlueZ ExchangeMTU) —
`{seq, total, sha256-of-full-payload, data(base64)}` — one frame per
write to chunk-rx. The receiver reassembles and verifies the
whole-payload sha256 **before** the packet is parsed or used. A
single flipped byte anywhere fails the transfer.

GATT profile (UUIDs are v0 placeholders, pinned in `ble_provision.py`):
service `fc-provision`; characteristics **control** (write — begin /
abort a session), **chunk-rx** (write — the frames), **status**
(read/notify — state only, never secrets). Arming is never a BLE
operation.

**Who may enroll — the armed window.** A fresh node holds no key, so
its trust root is physical: a person arms its provisioning window,
on the node itself. Then:

- Window disarmed or expired → every provisioning packet rejected.
- Window armed → the first packet whose signature verifies under the
  key it carries is accepted; the window closes itself (one-shot).
- A node that already holds the cluster key skips the window
  entirely and verifies at full strength against its own key;
  foreign-signed packets are always rejected.

Secret discipline: `ble_provision.py` never writes the PSK or key to
disk and never logs them. `accept_provisioning()` returns the config
in memory; the on-box service persists it under its own rules.

### Enrollment ceremony (what a person actually does)

1. Unbox / flash the node; power it on near any enrolled node.
2. On the fresh node, arm provisioning (console command or button —
   the on-box build's one local action). The window is open for
   10 minutes, once.
3. On any enrolled node, run the provision send with the new node's
   name, the WiFi SSID/PSK, and the cluster node map. It signs with
   the cluster key and sends the chunks over BLE.
4. The fresh node verifies, enrolls, and closes its window. Status
   characteristic reads `enrolled`.
5. The node joins WiFi, starts FC-Link, and appears in the next hub
   round like any other member. If anything failed, the window has
   expired or stayed closed — re-arm and retry; nothing half-enrolls.

No step needs a phone. A phone running a sender app is a convenience,
never a requirement.

## Honest limits

- BLE is narrow: with MTU 256 and the 2M PHY, practical throughput is
  roughly 1 Mbps on a good link — the Bluetooth PAN is in the same
  class. That is ample for signed envelopes, heartbeats, hash jobs,
  and provisioning packets (all KB-scale).
- Bulk stays on IP transports when they exist: file transfer,
  multi-MB payloads, and chain sync ride cable / WiFi / tailnet.
  Bluetooth is the underlay that is *always there* — provisioning a
  node that has nothing yet, and keeping command traffic moving when
  the infrastructure is gone — not a WiFi-speed replacement.
- BLE range is room-scale (~10 m class) without pairing to external
  antennas. Provisioning and fallback commands are local acts by
  design; anything farther belongs on the IP transports.
- A fresh node's enrollment security is exactly the armed window:
  whoever can arm the window and be in radio range during it can
  enroll the node. That is the intended ceremony — treat arming like
  handing someone the key, because it is.
