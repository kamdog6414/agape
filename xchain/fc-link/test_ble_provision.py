#!/usr/bin/env python3
"""test_ble_provision - plain-assert checks for ble_provision.py.

Pure logic, no Bluetooth hardware, no temp files, no real material:
every key and credential below is throwaway, generated in memory for
this run and never written anywhere. Run: python3 -B test_ble_provision.py
"""

import base64
import json
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ble_provision as ble

NOW = 1_800_000_000  # fixed clock so stale/replay cases are exact

KEY = secrets.token_bytes(32)
NODES = {
    "nikolai": "192.168.77.1",
    "roach": "192.168.77.3",
    "sov": "192.168.77.19",
    "sat": "192.168.254.2",
    "grandma-node": "192.168.1.50",
}


def make_packet(ts=NOW, nonce=None, signing_key=KEY, carried_key=KEY):
    return ble.build_packet(
        signing_key,
        node_name="grandma-node",
        ssid="ThrowawayNet-5G",
        psk="throwaway-psk-not-real",
        fclink_key=carried_key,
        cluster_nodes=NODES,
        ts=ts,
        nonce=nonce or secrets.token_hex(16),
    )


def reassemble(frames):
    r = ble.Reassembler()
    out = None
    for f in frames:
        got = r.feed(f)
        if got is not None:
            out = got
    return out


def expect_reject(fn, label):
    try:
        fn()
    except ble.ProvisionError:
        print("PASS reject: %s" % label)
        return
    raise AssertionError("expected ProvisionError: %s" % label)


# -- chunking: a realistic config is > MTU and takes several frames --
packet = make_packet()
payload = ble.serialize_packet(packet)
assert len(payload) > ble.MTU, "test config must exceed one MTU"
frames = ble.chunk_packet(packet)
assert len(frames) > 1, "expected >1 chunk for a realistic config"
assert all(len(f) <= ble.MTU for f in frames), "frame exceeds MTU"
print("PASS chunking: %d payload bytes -> %d frames, each <= %d bytes"
      % (len(payload), len(frames), ble.MTU))

# -- round-trip is byte-exact --
back = reassemble(frames)
assert back == payload, "reassembled payload differs from original"
parsed = json.loads(back.decode("utf-8"))
assert parsed == packet, "reassembled packet differs from original"
print("PASS round-trip: chunk -> reassemble is byte-exact")

# -- a flipped byte inside one chunk's data is rejected --------------
tampered = list(frames)
frame = json.loads(tampered[1].decode("utf-8"))
data = frame["data"]
frame["data"] = ("A" if data[0] != "A" else "B") + data[1:]
tampered[1] = json.dumps(frame, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
expect_reject(lambda: reassemble(tampered),
              "flipped chunk byte fails whole-payload sha256")

# -- signature tamper is rejected -------------------------------------
bad = make_packet()
bad["node_name"] = "mallory-node"  # edited after signing
expect_reject(
    lambda: ble.accept_provisioning(bad, known_key=KEY,
                                    seen_nonces=set(), now=NOW),
    "signature tamper (field edited after signing)")

# -- a packet signed by a different key is rejected by an enrolled node
alien = make_packet(signing_key=secrets.token_bytes(32),
                    carried_key=secrets.token_bytes(32))
expect_reject(
    lambda: ble.accept_provisioning(alien, known_key=KEY,
                                    seen_nonces=set(), now=NOW),
    "packet signed with a foreign key")

# -- stale timestamp is rejected ---------------------------------------
old = make_packet(ts=NOW - ble.TS_SKEW_S - 1000)
expect_reject(
    lambda: ble.accept_provisioning(old, known_key=KEY,
                                    seen_nonces=set(), now=NOW),
    "stale timestamp outside 300 s skew")

# -- replayed nonce is rejected ----------------------------------------
seen = set()
good = make_packet()
cfg = ble.accept_provisioning(good, known_key=KEY, seen_nonces=seen,
                              now=NOW)
assert cfg["node_name"] == "grandma-node"
assert cfg["fclink_key"] == KEY
assert cfg["cluster_nodes"] == NODES
print("PASS accept: enrolled node verifies and returns config in memory")
expect_reject(
    lambda: ble.accept_provisioning(good, known_key=KEY,
                                    seen_nonces=seen, now=NOW),
    "replayed nonce")

# -- disarmed window rejects a fresh-node enrollment -------------------
fresh = make_packet()
window = ble.ProvisioningWindow()
assert not window.is_armed(NOW)
expect_reject(
    lambda: ble.accept_provisioning(fresh, known_key=None,
                                    window=window, seen_nonces=set(),
                                    now=NOW),
    "disarmed window rejects a well-formed packet")
expect_reject(
    lambda: ble.accept_provisioning(fresh, known_key=None,
                                    window=None, seen_nonces=set(),
                                    now=NOW),
    "fresh node with no window object can never enroll")

# -- armed window: exactly one enrollment, then self-closes ------------
window = ble.ProvisioningWindow()
window.arm(seconds=600, now=NOW)
assert window.is_armed(NOW)
seen2 = set()
cfg = ble.accept_provisioning(make_packet(), known_key=None,
                              window=window, seen_nonces=seen2,
                              now=NOW)
assert cfg["ssid"] == "ThrowawayNet-5G"
assert cfg["fclink_key"] == KEY
assert not window.is_armed(NOW), "window must close after one enrollment"
print("PASS armed window: first enrollment accepted, window self-closed")
expect_reject(
    lambda: ble.accept_provisioning(make_packet(), known_key=None,
                                    window=window, seen_nonces=seen2,
                                    now=NOW),
    "second enrollment after the one-shot window closed")

# -- expired window rejects ---------------------------------------------
window = ble.ProvisioningWindow()
window.arm(seconds=60, now=NOW)
expect_reject(
    lambda: ble.accept_provisioning(make_packet(), known_key=None,
                                    window=window, seen_nonces=set(),
                                    now=NOW + 3600),
    "expired window")

print("PASS all ble_provision checks")
