#!/usr/bin/env python3
"""ble_provision - Bluetooth provisioning core for the Agape FC-Link layer.

REFERENCE CORE, NOT A BLUETOOTH DAEMON. This module is the hardware-free
protocol logic for BLE provisioning: packet format, signing, MTU chunking,
reassembly, and the enrollment gate. It opens no sockets, talks to no
Bluetooth adapter, and imports nothing outside the stdlib, so the whole
protocol is testable on any machine. The on-box BlueZ implementation (a
later build) owns the adapter and the GATT server; it feeds received
chunk bytes into Reassembler and hands the accepted config from
accept_provisioning() to the node's network setup. The GATT shape it
must expose is pinned below as data (GATT_PROFILE).

Two BLE roles in Agape (see BLE.md):

  1. Provisioning (this module). A fresh node with no screen and no
     keyboard receives its WiFi credentials, its FC-Link key, and its
     cluster identity over Bluetooth from any already-enrolled node.
     The phone is optional and never required.
  2. Transport. The same signed FC-Link envelopes ride Bluetooth
     directly (today: IP over the Bluetooth PAN, 192.168.79.1/24; the
     no-IP fallback is the same bytes chunked by this module's chunker
     over the chunk-rx characteristic).

Trust model, stated plainly:

  - A node that ALREADY holds the cluster key verifies the packet's
    signature against that key at full strength. Packets signed by any
    other key are rejected, window or no window.
  - A factory-fresh node holds no key, so there is nothing to verify
    against except the key the packet itself carries. Its signature
    check proves the packet is internally consistent -- authored by
    whoever holds the delivered key -- but the actual trust root for a
    fresh node is the founder-armed provisioning window: a human arms
    the window on the node (console or button), and only then is a
    first enrollment possible at all. The window is one-shot: the
    first accepted enrollment closes it. When the window is disarmed
    or expired, fresh-node provisioning is rejected outright.

Secret handling: the packet carries the WiFi PSK and the FC-Link key.
This module NEVER writes them to disk and NEVER logs or prints them.
accept_provisioning() returns the parsed config to its caller in
memory; persisting it is the caller's job, under the caller's rules.

Signing discipline is identical to fcl.py: HMAC-SHA256 over a canonical
body (JSON, sort_keys, compact separators), constant-time comparison,
timestamp skew <= 300 s, single-use nonces tracked in a caller-provided
seen-set (the caller owns persistence of that set, as fclinkd does for
HTTP nonces).

Stdlib only. No real keys or credentials appear in this file; tests
generate throwaway material in memory.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

# BLE MTU on the cluster boxes: BlueZ ExchangeMTU=256 (set by the
# musegadget install). One chunk frame must fit in a single write.
MTU = 256

# Raw payload bytes per chunk. The frame is JSON
# {"seq":N,"total":M,"sha256":"<64 hex>","data":"<base64>"}; 96 raw
# bytes -> 128 base64 chars leaves the frame at ~230 bytes worst case,
# under the 256 MTU. chunk_payload() asserts the bound on every frame.
CHUNK_RAW = 96

PROTOCOL_V = 1
TS_SKEW_S = 300

# ---------------------------------------------------------------------
# GATT shape, as data. The on-box BlueZ implementation exposes exactly
# this profile; UUIDs are v0 PLACEHOLDERS on a FullCircle vendor base
# (fc1c = "FC-Link Cluster"), chosen for this build and not registered
# anywhere. The on-box build may renumber, but must keep the three
# characteristics and their properties.
# ---------------------------------------------------------------------
GATT_UUID_BASE = "fc1c0000-4655-4c4c-8000-000000000000"  # placeholder

GATT_PROFILE = {
    "service": {
        "name": "fc-provision",
        "uuid": "fc1c1000-4655-4c4c-8000-000000000000",  # placeholder
        "primary": True,
    },
    "characteristics": [
        {
            "name": "control",
            "uuid": "fc1c1001-4655-4c4c-8000-000000000000",  # placeholder
            "properties": ["write"],
            # JSON ops: {"op":"begin"} opens a reassembly session,
            # {"op":"abort"} drops it. Arming the provisioning window
            # is NEVER a BLE op -- a human arms it on the node itself.
            "payload": "json op",
        },
        {
            "name": "chunk-rx",
            "uuid": "fc1c1002-4655-4c4c-8000-000000000000",  # placeholder
            "properties": ["write", "write-without-response"],
            "payload": "one chunk_payload() frame per write, in seq order",
        },
        {
            "name": "status",
            "uuid": "fc1c1003-4655-4c4c-8000-000000000000",  # placeholder
            "properties": ["read", "notify"],
            # JSON {"state": idle|receiving|enrolled|rejected, ...}.
            # Status NEVER carries ssid, psk, key material, or nonces.
            "payload": "json status, no secrets",
        },
    ],
}


class ProvisionError(Exception):
    """Any provisioning rejection: bad frame, bad hash, bad signature,
    stale or replayed packet, or a closed provisioning window."""


# ---------------------------------------------------------------------
# Packet: build + sign
# ---------------------------------------------------------------------
def canonical_body(packet):
    """The signed bytes: the packet without its "sig" field, canonical
    JSON (sort_keys, compact separators), UTF-8."""
    body = {k: v for k, v in packet.items() if k != "sig"}
    return json.dumps(body, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sign_packet(key, packet):
    return hmac.new(key, canonical_body(packet),
                    hashlib.sha256).hexdigest()


def verify_packet(key, packet):
    sig = packet.get("sig")
    if not isinstance(sig, str):
        return False
    return hmac.compare_digest(sig, sign_packet(key, packet))


def build_packet(signing_key, *, node_name, ssid, psk, fclink_key,
                 cluster_nodes, ts=None, nonce=None):
    """Build and sign one provisioning packet.

    signing_key: the cluster FC-Link key (bytes). In normal operation
    it IS fclink_key -- the packet delivers the very key it is signed
    with, which is what lets an enrolled peer verify it at full
    strength. fclink_key is carried base64 in the packet; psk is
    carried as text, as WiFi config consumes it that way. ts/nonce are
    injectable for tests; production callers leave both None.
    cluster_nodes: {name: host} map for the cluster block.
    """
    if ts is None:
        ts = int(time.time())
    if nonce is None:
        nonce = secrets.token_hex(16)
    packet = {
        "v": PROTOCOL_V,
        "node_name": node_name,
        "ssid": ssid,
        "psk": psk,
        "fclink_key_b64": base64.b64encode(fclink_key).decode("ascii"),
        "cluster": {"nodes": dict(cluster_nodes)},
        "ts": int(ts),
        "nonce": nonce,
    }
    packet["sig"] = sign_packet(signing_key, packet)
    return packet


def serialize_packet(packet):
    """The exact payload bytes that get chunked: the full packet,
    signature included, canonical JSON."""
    return json.dumps(packet, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


# ---------------------------------------------------------------------
# Chunking for the BLE MTU
# ---------------------------------------------------------------------
def chunk_payload(payload, mtu=MTU):
    """Split payload bytes into BLE-sized frames.

    Each frame is canonical-JSON bytes:
      {"seq": i, "total": n, "sha256": <hex sha256 of the WHOLE
       payload>, "data": <base64 of this slice>}
    Every frame is asserted <= mtu bytes. Frames go on the wire one
    per write to the chunk-rx characteristic, in seq order (the
    reassembler also tolerates out-of-order arrival).
    """
    digest = hashlib.sha256(payload).hexdigest()
    slices = [payload[i:i + CHUNK_RAW]
              for i in range(0, len(payload), CHUNK_RAW)] or [b""]
    frames = []
    for seq, sl in enumerate(slices):
        frame = {
            "seq": seq,
            "total": len(slices),
            "sha256": digest,
            "data": base64.b64encode(sl).decode("ascii"),
        }
        raw = json.dumps(frame, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
        assert len(raw) <= mtu, "chunk frame exceeds MTU"
        frames.append(raw)
    return frames


def chunk_packet(packet, mtu=MTU):
    return chunk_payload(serialize_packet(packet), mtu=mtu)


class Reassembler:
    """Collects chunk frames back into the payload they came from.

    feed() returns None until every slice is present, then verifies
    the whole-payload sha256 and returns the payload bytes. Any
    inconsistency -- a frame that disagrees on total/sha256, a seq out
    of range, a conflicting duplicate, or a final hash mismatch --
    raises ProvisionError and poisons the session (start over with a
    fresh Reassembler, matching a fresh {"op":"begin"}).
    """

    def __init__(self):
        self._total = None
        self._sha256 = None
        self._slices = {}
        self._done = False

    def feed(self, frame_bytes):
        if self._done:
            raise ProvisionError("reassembly already complete")
        try:
            frame = json.loads(frame_bytes.decode("utf-8"))
            seq = frame["seq"]
            total = frame["total"]
            digest = frame["sha256"]
            data = base64.b64decode(frame["data"], validate=True)
        except (ValueError, KeyError, TypeError, UnicodeDecodeError) \
                as exc:
            raise ProvisionError("malformed chunk frame: %s" % exc)
        if not isinstance(seq, int) or not isinstance(total, int) \
                or total < 1 or not (0 <= seq < total):
            raise ProvisionError("chunk seq/total out of range")
        if self._total is None:
            self._total, self._sha256 = total, digest
        elif total != self._total or digest != self._sha256:
            raise ProvisionError("chunk disagrees on total/sha256")
        if seq in self._slices and self._slices[seq] != data:
            raise ProvisionError("conflicting data for seq %d" % seq)
        self._slices[seq] = data
        if len(self._slices) < self._total:
            return None
        payload = b"".join(self._slices[i] for i in range(self._total))
        if hashlib.sha256(payload).hexdigest() != self._sha256:
            raise ProvisionError("payload sha256 mismatch after "
                                 "reassembly -- rejecting")
        self._done = True
        return payload


# ---------------------------------------------------------------------
# The founder-armed provisioning window (fresh-node trust root)
# ---------------------------------------------------------------------
class ProvisioningWindow:
    """Explicit arm/disarm state for factory-fresh enrollment.

    Disarmed by default. arm() opens the window for a bounded time;
    consume() is called by accept_provisioning() after the FIRST
    successful fresh-node enrollment and closes the window
    immediately -- one-shot by construction. There is no BLE-reachable
    way to arm it: arming is a local, human act on the node.
    """

    def __init__(self):
        self._expires_at = None

    def arm(self, seconds=600, now=None):
        if now is None:
            now = time.time()
        self._expires_at = now + seconds

    def disarm(self):
        self._expires_at = None

    def is_armed(self, now=None):
        if self._expires_at is None:
            return False
        if now is None:
            now = time.time()
        if now > self._expires_at:
            self._expires_at = None  # lazily expire
            return False
        return True

    def consume(self):
        """Close the window after one enrollment. Returns True if it
        was armed (the expected path), False otherwise."""
        was = self._expires_at is not None
        self._expires_at = None
        return was


# ---------------------------------------------------------------------
# Acceptance: the enrollment gate
# ---------------------------------------------------------------------
def accept_provisioning(packet, *, known_key=None, window=None,
                        seen_nonces=None, now=None):
    """Verify one parsed provisioning packet and return its config.

    known_key: the cluster key this node already holds, or None for a
    factory-fresh node. window: a ProvisioningWindow, REQUIRED when
    known_key is None (a fresh node with no window object can never
    enroll). seen_nonces: caller-provided set of spent nonces; the
    packet's nonce is added only on success. now: injectable clock.

    Returns {"node_name", "ssid", "psk", "fclink_key" (bytes),
    "cluster_nodes"} in memory only. Raises ProvisionError on any
    rejection; the reason never includes secret material.
    """
    if now is None:
        now = int(time.time())
    if not isinstance(packet, dict):
        raise ProvisionError("packet is not a JSON object")
    if packet.get("v") != PROTOCOL_V:
        raise ProvisionError("unsupported packet version: %r"
                             % (packet.get("v"),))
    ts = packet.get("ts")
    if not isinstance(ts, int) or abs(now - ts) > TS_SKEW_S:
        raise ProvisionError("packet timestamp outside %ds skew"
                             % TS_SKEW_S)
    nonce = packet.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        raise ProvisionError("packet has no nonce")
    if seen_nonces is not None and nonce in seen_nonces:
        raise ProvisionError("replayed nonce")

    try:
        carried_key = base64.b64decode(packet["fclink_key_b64"],
                                       validate=True)
    except (ValueError, KeyError, TypeError) as exc:
        raise ProvisionError("packet carries no usable key: %s" % exc)
    if not carried_key:
        raise ProvisionError("packet carries an empty key")

    if known_key is not None:
        # Enrolled node: full-strength check against the key it holds.
        if not verify_packet(known_key, packet):
            raise ProvisionError("signature does not verify under "
                                 "the cluster key this node holds")
    else:
        # Factory-fresh node: the armed window is the trust root. The
        # signature must still verify under the key the packet itself
        # carries (authored by the holder of the delivered key).
        if window is None or not window.is_armed(now):
            raise ProvisionError("provisioning window is not armed")
        if not verify_packet(carried_key, packet):
            raise ProvisionError("signature does not verify under "
                                 "the key the packet carries")
        window.consume()  # one-shot: first enrollment closes it

    nodes = packet.get("cluster", {}).get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        raise ProvisionError("packet carries no cluster node map")
    for field in ("node_name", "ssid", "psk"):
        if not isinstance(packet.get(field), str) \
                or not packet[field]:
            raise ProvisionError("packet missing field: %s" % field)

    if seen_nonces is not None:
        seen_nonces.add(nonce)
    return {
        "node_name": packet["node_name"],
        "ssid": packet["ssid"],
        "psk": packet["psk"],
        "fclink_key": carried_key,
        "cluster_nodes": nodes,
    }
