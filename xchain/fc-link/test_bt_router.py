#!/usr/bin/env python3
"""test_bt_router - plain-assert checks for bt_router.py.

Pure logic: no Bluetooth hardware, no root, no system changes. The
executor is only ever called DISARMED here (plus once through an
injected recording runner, which is how the armed path is checked
without executing anything real). Every key is throwaway, generated
in memory. Run: python3 -B test_bt_router.py
"""

import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bt_router as br

NOW = 1_800_000_000  # fixed clock so stale/replay cases are exact
KEY = secrets.token_bytes(32)


def expect_reject(fn, label, exc=br.RouterError):
    try:
        fn()
    except exc:
        print("PASS reject: %s" % label)
        return
    raise AssertionError("expected %s: %s" % (exc.__name__, label))


# -- address plan: hub-0 keeps the fleet subnet, plan is stable ------
def hubs(n):
    return [br.make_hub(i, "node-%d" % i,
                        uplink_iface="wlan0", uplink_kind="wifi",
                        metric=10 * (i + 1)) for i in range(n)]

for n in (1, 2, 3, 4):
    plan = br.plan_subnets(hubs(n))
    assert len(plan) == n and len(set(plan.values())) == n, \
        "plan for %d hubs must be collision-free" % n
    assert plan["hub-0"] == "192.168.79.0/24", \
        "hub-0 must keep the fleet PAN subnet"
    for i in range(n):
        assert plan["hub-%d" % i] == "192.168.%d.0/24" % (79 + i)
    again = br.plan_subnets(hubs(n))
    assert again == plan, "plan must be deterministic"
    if n > 1:
        smaller = br.plan_subnets(hubs(n - 1))
        for hid, subnet in smaller.items():
            assert plan[hid] == subnet, \
                "appending a hub must not renumber %s" % hid
print("PASS address plan: 1..4 hubs deterministic, collision-free, "
      "hub-0 = 192.168.79.0/24, append-stable")

expect_reject(lambda: br.plan_subnets(hubs(2) + [br.make_hub(
    1, "dupe", uplink_iface="wlan0", uplink_kind="wifi")]),
    "duplicate hub_index refused")
drifted = br.make_hub(1, "drifty", uplink_iface="wlan0",
                      uplink_kind="wifi")
drifted["subnet"] = "192.168.99.0/24"
expect_reject(lambda: br.plan_subnets([drifted]),
              "hub whose declared subnet disagrees with the plan")

# -- dnsmasq render: right range, right router, own subnet only -------
hub0 = br.make_hub(0, "nikolai", uplink_iface="wlan0",
                   uplink_kind="wifi", metric=10)
cfg = br.render_dnsmasq(hub0)
assert "interface=bnep0" in cfg
assert "dhcp-range=192.168.79.10,192.168.79.200,255.255.255.0,12h" \
    in cfg
assert "dhcp-option=3,192.168.79.1" in cfg, "router option = hub .1"
assert "192.168.80." not in cfg, "a hub serves only its own /24"
hub2 = br.make_hub(2, "jupi", uplink_iface="bnep0",
                   uplink_kind="pan", metric=30, serve_iface="bnep1")
cfg2 = br.render_dnsmasq(hub2)
assert "interface=bnep1" in cfg2
assert "dhcp-range=192.168.81.10,192.168.81.200" in cfg2
assert "dhcp-option=3,192.168.81.1" in cfg2
print("PASS dnsmasq render: per-hub range + router inside its own /24")

# -- nft render: NAT only on the uplink, forward default-drop ---------
rules = br.render_nft(hub0)
assert 'oifname "wlan0" masquerade' in rules
assert rules.count("masquerade") == 1, "exactly one NAT rule"
assert 'oifname "bnep0" masquerade' not in rules
assert "policy drop" in rules, "forward chain must default-drop"
assert 'iifname "bnep0" oifname "wlan0" accept' in rules
assert "established,related" in rules
dark = br.make_hub(1, "dark-hub")  # no uplink at all
dark_rules = br.render_nft(dark)
assert "masquerade" not in dark_rules, "no uplink -> no NAT"
assert "policy drop" in dark_rules
print("PASS nft render: masquerade only on uplink iface, "
      "forward policy drop, no-uplink hub forwards nothing")

assert br.render_ip_forward_cmd() == \
    ["sysctl", "-w", "net.ipv4.ip_forward=1"]
print("PASS ip_forward is a rendered command, not a silent act")

# -- announcements: sign/verify round-trip -----------------------------
ann = br.build_announcement(KEY, hub0, ts=NOW, nonce="n-roundtrip")
got = br.verify_announcement(KEY, ann, seen_nonces=set(), now=NOW)
assert got == {"hub_id": "hub-0", "node_name": "nikolai",
               "subnet": "192.168.79.0/24", "uplink_kind": "wifi",
               "metric": 10}
print("PASS announcement: sign/verify round-trip returns hub fields")

# -- tampered metric is rejected (edit after signing) ------------------
bad = br.build_announcement(KEY, hub0, ts=NOW, nonce="n-tamper")
bad["metric"] = 1  # suddenly the best hub in the world
expect_reject(lambda: br.verify_announcement(
    KEY, bad, seen_nonces=set(), now=NOW),
    "tampered metric fails signature")

# -- stale timestamp is rejected ----------------------------------------
old = br.build_announcement(KEY, hub0, ts=NOW - br.TS_SKEW_S - 1000,
                            nonce="n-stale")
expect_reject(lambda: br.verify_announcement(
    KEY, old, seen_nonces=set(), now=NOW),
    "stale timestamp outside 300 s skew")

# -- replayed nonce is rejected ------------------------------------------
seen = set()
fresh = br.build_announcement(KEY, hub0, ts=NOW, nonce="n-replay")
br.verify_announcement(KEY, fresh, seen_nonces=seen, now=NOW)
assert "n-replay" in seen
expect_reject(lambda: br.verify_announcement(
    KEY, fresh, seen_nonces=seen, now=NOW), "replayed nonce")

# -- foreign key is rejected ----------------------------------------------
alien = br.build_announcement(secrets.token_bytes(32), hub0, ts=NOW,
                              nonce="n-alien")
expect_reject(lambda: br.verify_announcement(
    KEY, alien, seen_nonces=set(), now=NOW),
    "announcement signed with a foreign key")

# -- select_hub: lowest metric with uplink; junk never selected ----------
h_root = br.make_hub(0, "nikolai", uplink_iface="wlan0",
                     uplink_kind="wifi", metric=10)
h_far = br.make_hub(1, "roach", uplink_iface="bnep0",
                    uplink_kind="pan", metric=20)
h_local = br.make_hub(2, "dark", metric=0)  # no uplink, best metric
anns = [
    br.build_announcement(KEY, h_far, ts=NOW, nonce="s-far"),
    br.build_announcement(KEY, h_local, ts=NOW, nonce="s-local"),
    br.build_announcement(KEY, h_root, ts=NOW, nonce="s-root"),
]
picked = br.select_hub(anns, KEY, want_uplink=True,
                       seen_nonces=set(), now=NOW)
assert picked["hub_id"] == "hub-0" and picked["metric"] == 10, \
    "lowest-metric UPLINK hub wins; the metric-0 no-uplink hub is " \
    "not an uplink"
picked_any = br.select_hub(anns, KEY, want_uplink=False,
                           seen_nonces=set(), now=NOW)
assert picked_any["hub_id"] == "hub-2", \
    "without the uplink requirement, lowest metric overall wins"
forged = br.build_announcement(KEY, h_root, ts=NOW, nonce="s-forged")
forged["metric"] = -1 if False else 0  # edited after signing: invalid
forged["node_name"] = "mallory"
picked2 = br.select_hub([forged] + anns, KEY, want_uplink=True,
                        seen_nonces=set(), now=NOW)
assert picked2["hub_id"] == "hub-0" and \
    picked2["node_name"] == "nikolai", \
    "a tampered announcement is skipped, never selected"
assert br.select_hub([forged], KEY, seen_nonces=set(), now=NOW) \
    is None, "only junk on offer -> no hub selected"
print("PASS select_hub: lowest-metric verified uplink hub; "
      "unverifiable announcements are never selected")

# -- chain_plan: leaf -> hub -> hub -> internet ---------------------------
nodes = [
    {"node_name": "core", "uplink_kind": "wifi",
     "uplink_iface": "wlan0", "via": None, "serves": True},
    {"node_name": "relay", "uplink_kind": "pan",
     "via": "core", "serves": True},
    {"node_name": "leaf", "uplink_kind": "none",
     "via": "relay", "serves": False},
]
entries = br.chain_plan(nodes)
by_name = {e["node_name"]: e for e in entries}
assert by_name["core"]["role"] == "root-hub"
assert by_name["relay"]["role"] == "chained-hub"
assert by_name["leaf"]["role"] == "leaf"
assert by_name["core"]["metric"] == 10
assert by_name["relay"]["metric"] == 20, "metric grows one hop out"
assert by_name["relay"]["depth"] == 1 and \
    by_name["leaf"]["depth"] == 2
assert by_name["core"]["hub"]["subnet"] == "192.168.79.0/24"
assert by_name["relay"]["hub"]["subnet"] == "192.168.80.0/24"
assert by_name["relay"]["hub"]["uplink_kind"] == "pan"
assert by_name["relay"]["hub"]["uplink_iface"] == "bnep0"
assert by_name["relay"]["hub"]["serve_iface"] == "bnep1"
order = [e["node_name"] for e in entries]
assert order.index("core") < order.index("relay") \
    < order.index("leaf"), "parents come before children"
print("PASS chain_plan: leaf -> chained hub -> root hub -> internet, "
      "metrics 10 -> 20, subnets 79 -> 80")

expect_reject(lambda: br.chain_plan([
    {"node_name": "a", "uplink_kind": "pan", "via": "b",
     "serves": True},
    {"node_name": "b", "uplink_kind": "pan", "via": "a",
     "serves": True}]),
    "a via-cycle is refused")
expect_reject(lambda: br.chain_plan([
    {"node_name": "orphan", "uplink_kind": "none",
     "via": "ghost", "serves": False}]),
    "a dangling via pointer is refused")
expect_reject(lambda: br.chain_plan([
    {"node_name": "core", "uplink_kind": "wifi",
     "uplink_iface": "wlan0", "via": None, "serves": True},
    {"node_name": "bad", "uplink_kind": "pan", "via": "plain",
     "serves": True},
    {"node_name": "plain", "uplink_kind": "wifi",
     "uplink_iface": "wlan0", "via": None, "serves": False}]),
    "chaining via a non-serving node is refused")

# -- render_plan: step order for the 2-hub chain ---------------------------
plan = br.render_plan(entries)
assert [s["order"] for s in plan] == list(range(len(plan))), \
    "orders are sequential"
kinds = [(s["node"], s["step"]) for s in plan]
core_dns = kinds.index(("core", "dnsmasq"))
relay_join = kinds.index(("relay", "panu-connect"))
relay_dns = kinds.index(("relay", "dnsmasq"))
leaf_join = kinds.index(("leaf", "panu-connect"))
assert core_dns < relay_join, \
    "the parent hub serves before the chained hub joins it"
assert relay_join < relay_dns, \
    "a chained hub joins its parent before serving its own PAN"
assert relay_dns < leaf_join, "hubs stand up before leaves join"
core_nft = next(s for s in plan
                if s["node"] == "core" and s["step"] == "nft")
assert 'oifname "wlan0" masquerade' in core_nft["config"]
relay_nft = next(s for s in plan
                 if s["node"] == "relay" and s["step"] == "nft")
assert 'oifname "bnep0" masquerade' in relay_nft["config"], \
    "a chained hub NATs onto its PAN uplink"
assert not any(s["step"] == "default-route" for s in plan), \
    "no BT default route unless armed / primary-down"
armed_plan = br.render_plan(entries, bt_default=True)
defaults = [s for s in armed_plan if s["step"] == "default-route"]
assert len(defaults) == 1 and defaults[0]["node"] == "leaf"
assert defaults[0]["argv"][-2:] == ["metric",
                                    str(br.BT_DEFAULT_METRIC)]
print("PASS render_plan: parent serves -> chained hub joins -> "
      "chained hub serves -> leaf joins; BT default route only "
      "when armed, at a poor metric")

# -- execute_plan: refused while disarmed, runs in order when armed -------
expect_reject(lambda: br.execute_plan(plan),
              "execute_plan with armed=False refuses")
expect_reject(lambda: br.execute_plan(plan, armed=br.RouterArm()),
              "execute_plan behind an un-armed RouterArm refuses")
ran = []
gate = br.RouterArm()
gate.arm(seconds=600, now=NOW)
# the injected clock only arms the gate; execution itself is real-time
gate2 = br.RouterArm()
gate2.arm(seconds=600)
done = br.execute_plan(plan, armed=gate2,
                       runner=lambda step: ran.append(step["step"]))
assert done == [s["step"] for s in plan]
assert ran == done, "runner received every step in plan order"
print("PASS execute_plan: disarmed refuses; armed runs the rendered "
      "steps in order (via injected runner)")

print("PASS all bt_router checks")
