#!/usr/bin/env python3
"""bt_router - Bluetooth PAN routing core for the Agape FC-Link layer.

REFERENCE CORE, NOT A NETWORK DAEMON. This module is the hardware-free
logic for running Agape as a central Bluetooth hub: topology and
address planning, hub/client config renders, signed hub announcements,
hub selection and chaining, and an ordered apply plan. It opens no
sockets, touches no adapter, and changes no system state: every system
effect is rendered as DATA (an ordered command plan), and the only
executor refuses to run unless explicitly armed. The on-box build (a
later, separately approved step) owns BlueZ, dnsmasq, and nftables on
each box and feeds this module's renders to them.

What this adds over ble_provision.py: provisioning hands a fresh node
its config over BLE; transport moves signed envelopes over an existing
PAN link. This module is the missing middle -- full IP networking over
Bluetooth. A hub with a WiFi or Ethernet uplink SHARES that uplink to
its Bluetooth PAN clients by routing and NAT, the way a phone hotspot
shares its radio. A client with no uplink of its own can in turn
re-serve, so hubs chain: leaf -> hub -> hub -> internet. Agape is the
hub protocol: hubs announce themselves signed, clients pick the best
verified hub, and every address comes from one deterministic plan.

Topology rules, stated plainly:

  - ROUTED, never bridged. Each hub serves its own /24 and routes
    between its PAN interface and its uplink. Bridging chained PANs
    would merge broadcast domains across a tree whose shape changes
    as nodes join and leave -- spanning tree over intermittently
    present BNEP links is a loop generator. Routed hops keep each
    PAN an independent failure domain and make the address plan
    (below) possible at all.
  - Address plan: hub-0 keeps the fleet's existing PAN subnet,
    192.168.79.0/24 (Nikolai holds 192.168.79.1 today, via
    fclink-bt.service). Hub index i serves 192.168.(79+i).0/24; the
    hub itself is always address .1 in its subnet. Indices are
    assigned root-hubs first, then chained hubs by depth, so adding
    a hub at the end never renumbers an existing one.
  - Metric discipline: a hub advertises metric 10 per hop from an
    internet uplink (root hub 10, its chained child 20, ...). A
    client installs routes to the hub's served cluster networks
    always, but the DEFAULT route via Bluetooth only when its own
    primary is down or an operator armed it -- and even then at a
    poor metric, so a returning primary wins. Bluetooth must never
    silently hijack a working primary link.
  - Forwarding is fail-closed: a hub forwards only between its PAN
    interface and its uplink (plus established/related return
    traffic). Everything else drops. Cluster subnets are reachable;
    arbitrary forwarding is not a thing this module grants.

Platform honesty:

  - Linux boxes (Nikolai, Roach, JUPI) can run BlueZ BNEP in NAP
    (hub) or PANU (client) role today.
  - SOV's Bluetooth PAN is hosted by WINDOWS (the 192.168.79.x
    presence dates from the fclink-bt era; the link partner is the
    Windows Bluetooth stack, not WSL). This module therefore models
    SOV as a PAN participant reached at its Windows-hosted PAN
    address. It does NOT claim WSL can own BNEP -- it cannot; BNEP
    terminates in the Windows stack. Any SOV hub role would be a
    Windows-side configuration, out of scope for this Linux core.

Firewall choice: nftables. It is the current Linux firewall
front-end, and a whole ruleset renders as one text file applied
atomically with `nft -f`, which suits this module's render-then-arm
discipline (iptables restores piecemeal by comparison).

Signing discipline is ble_provision.py's, imported not re-implemented:
HMAC-SHA256 over canonical JSON (sort_keys, compact separators),
constant-time comparison, timestamp skew <= 300 s, single-use nonces
in a caller-provided seen-set.

Stdlib only. No real keys or credentials appear in this file; tests
generate throwaway material in memory.
"""

import ipaddress
import json
import secrets
import time

import ble_provision as ble

# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------
ANNOUNCE_V = 1
ANNOUNCE_KIND = "agape-hub-announce"
TS_SKEW_S = ble.TS_SKEW_S  # 300 s, same discipline as provisioning

BASE_THIRD_OCTET = 79       # hub-0: 192.168.79.0/24 (fleet fact)
MAX_HUB_INDEX = 255 - BASE_THIRD_OCTET
METRIC_PER_HOP = 10
BT_DEFAULT_METRIC = 600     # poor on purpose: a returning primary wins

UPLINK_KINDS = ("wifi", "ethernet", "pan", "none")

CONFIG_DIR = "/etc/agape/bt-router"  # where rendered configs land on-box


class RouterError(Exception):
    """Any router rejection: bad plan, bad announcement, disarmed
    execution, or an inconsistent topology."""


# ---------------------------------------------------------------------
# Address plan + hub model
# ---------------------------------------------------------------------
def subnet_for_index(hub_index):
    """Hub index -> its served subnet. hub-0 is the fleet's existing
    192.168.79.0/24; index i serves 192.168.(79+i).0/24."""
    if not isinstance(hub_index, int) or hub_index < 0 \
            or hub_index > MAX_HUB_INDEX:
        raise RouterError("hub_index out of range: %r" % (hub_index,))
    return "192.168.%d.0/24" % (BASE_THIRD_OCTET + hub_index)


def hub_address(subnet):
    """The hub's own address in its served subnet: always .1."""
    net = ipaddress.IPv4Network(subnet)
    return str(net.network_address + 1)


def make_hub(hub_index, node_name, uplink_iface=None, uplink_kind="none",
             metric=0, serve_iface="bnep0"):
    """One hub record: {hub_id, hub_index, node_name, subnet, address,
    uplink_iface, uplink_kind, metric, serve_iface}.

    uplink_kind "none" requires uplink_iface None (a hub with no
    uplink serves its PAN locally and chains nothing yet). A chained
    hub has uplink_kind "pan" and its uplink_iface is the BNEP
    interface toward its parent hub.
    """
    if uplink_kind not in UPLINK_KINDS:
        raise RouterError("uplink_kind must be one of %r, got %r"
                          % (UPLINK_KINDS, uplink_kind))
    if uplink_kind == "none" and uplink_iface is not None:
        raise RouterError("uplink_kind 'none' with an uplink_iface "
                          "is inconsistent")
    if uplink_kind != "none" and not uplink_iface:
        raise RouterError("uplink_kind %r needs an uplink_iface"
                          % (uplink_kind,))
    subnet = subnet_for_index(hub_index)
    return {
        "hub_id": "hub-%d" % hub_index,
        "hub_index": hub_index,
        "node_name": node_name,
        "subnet": subnet,
        "address": hub_address(subnet),
        "uplink_iface": uplink_iface,
        "uplink_kind": uplink_kind,
        "metric": metric,
        "serve_iface": serve_iface,
    }


def plan_subnets(hubs):
    """Assign subnets to a list of hub records -> {hub_id: subnet}.

    Deterministic and collision-free by construction: the subnet is
    a pure function of hub_index, indices must be unique, and a hub
    record that already carries a subnet must agree with the plan
    (a disagreement means someone's state drifted -- fail closed
    rather than renumber anyone). Appending a hub with the next free
    index never changes an existing assignment.
    """
    out = {}
    seen_index = {}
    for hub in hubs:
        hub_id = hub.get("hub_id")
        idx = hub.get("hub_index")
        if not hub_id or not isinstance(idx, int):
            raise RouterError("hub record missing hub_id/hub_index: "
                              "%r" % (hub,))
        if hub_id in out:
            raise RouterError("duplicate hub_id: %s" % hub_id)
        if idx in seen_index:
            raise RouterError("hub_index %d claimed by both %s and %s"
                              % (idx, seen_index[idx], hub_id))
        subnet = subnet_for_index(idx)
        if hub.get("subnet") is not None and hub["subnet"] != subnet:
            raise RouterError("%s declares subnet %s but the plan "
                              "assigns %s -- refusing to renumber"
                              % (hub_id, hub["subnet"], subnet))
        seen_index[idx] = hub_id
        out[hub_id] = subnet
    return out


# ---------------------------------------------------------------------
# Config renders (pure: hub record in, text out)
# ---------------------------------------------------------------------
def _dhcp_range(subnet):
    net = ipaddress.IPv4Network(subnet)
    return (str(net.network_address + 10),
            str(net.network_address + 200),
            str(net.netmask))


def render_dnsmasq(hub):
    """dnsmasq config for one hub: serve DHCP on the hub's PAN
    interface, inside its own /24 only, handing out the hub itself
    as router and DNS. The hub runs dnsmasq as a forwarder to its
    uplink's resolver, so clients need no other DNS config."""
    lo, hi, mask = _dhcp_range(hub["subnet"])
    lines = [
        "# agape bt_router hub config for %s (%s) -- rendered, "
        "do not hand-edit" % (hub["hub_id"], hub["node_name"]),
        "interface=%s" % hub["serve_iface"],
        "bind-interfaces",
        "dhcp-range=%s,%s,%s,12h" % (lo, hi, mask),
        "dhcp-option=3,%s" % hub["address"],   # router = the hub
        "dhcp-option=6,%s" % hub["address"],   # DNS = the hub (forwards)
    ]
    return "\n".join(lines) + "\n"


def render_nft(hub):
    """nftables ruleset for one hub.

    NAT: masquerade ONLY on the uplink interface. Forward: PAN ->
    uplink accepted, uplink -> PAN only for established/related
    return traffic, chain policy drop -- a hub with no uplink gets
    the drop policy and no NAT at all (fail-closed: it can serve its
    own PAN locally but forwards nothing anywhere).
    """
    pan = hub["serve_iface"]
    up = hub.get("uplink_iface")
    lines = [
        "# agape bt_router ruleset for %s (%s) -- rendered, "
        "do not hand-edit" % (hub["hub_id"], hub["node_name"]),
        "table ip agape_bt {",
        "    chain forward {",
        "        type filter hook forward priority 0; policy drop;",
    ]
    if up:
        lines += [
            '        iifname "%s" oifname "%s" accept' % (pan, up),
            '        iifname "%s" oifname "%s" ct state '
            'established,related accept' % (up, pan),
        ]
    lines += [
        "    }",
    ]
    if up:
        lines += [
            "    chain postrouting {",
            "        type nat hook postrouting priority 100; "
            "policy accept;",
            '        oifname "%s" masquerade' % up,
            "    }",
        ]
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_ip_forward_cmd():
    """Enabling IPv4 forwarding is a rendered command, never a
    silent act of this module. It appears in plans as data and runs
    only through the armed executor."""
    return ["sysctl", "-w", "net.ipv4.ip_forward=1"]


# ---------------------------------------------------------------------
# Signed hub announcements (signing imported from ble_provision)
# ---------------------------------------------------------------------
def build_announcement(key, hub, ts=None, nonce=None):
    """Build and sign one hub announcement:
    {v, kind, hub_id, node_name, subnet, uplink_kind, metric,
     ts, nonce, sig}. Signed with ble_provision's canonical-body
    HMAC scheme -- imported, not re-implemented."""
    if ts is None:
        ts = int(time.time())
    if nonce is None:
        nonce = secrets.token_hex(16)
    ann = {
        "v": ANNOUNCE_V,
        "kind": ANNOUNCE_KIND,
        "hub_id": hub["hub_id"],
        "node_name": hub["node_name"],
        "subnet": hub["subnet"],
        "uplink_kind": hub["uplink_kind"],
        "metric": hub["metric"],
        "ts": int(ts),
        "nonce": nonce,
    }
    ann["sig"] = ble.sign_packet(key, ann)
    return ann


def verify_announcement(key, ann, seen_nonces=None, now=None):
    """Verify one announcement and return its hub fields. Raises
    RouterError on anything stale, replayed, tampered, foreign, or
    malformed. The nonce is spent only on success, mirroring
    ble_provision.accept_provisioning."""
    if now is None:
        now = int(time.time())
    if not isinstance(ann, dict):
        raise RouterError("announcement is not a JSON object")
    if ann.get("v") != ANNOUNCE_V or ann.get("kind") != ANNOUNCE_KIND:
        raise RouterError("not an agape hub announcement")
    ts = ann.get("ts")
    if not isinstance(ts, int) or abs(now - ts) > TS_SKEW_S:
        raise RouterError("announcement timestamp outside %ds skew"
                          % TS_SKEW_S)
    nonce = ann.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        raise RouterError("announcement has no nonce")
    if seen_nonces is not None and nonce in seen_nonces:
        raise RouterError("replayed nonce")
    if not ble.verify_packet(key, ann):
        raise RouterError("announcement signature does not verify "
                          "under the cluster key")
    for field in ("hub_id", "node_name", "subnet"):
        if not isinstance(ann.get(field), str) or not ann[field]:
            raise RouterError("announcement missing field: %s" % field)
    if ann.get("uplink_kind") not in UPLINK_KINDS:
        raise RouterError("announcement has bad uplink_kind: %r"
                          % (ann.get("uplink_kind"),))
    if not isinstance(ann.get("metric"), int) or ann["metric"] < 0:
        raise RouterError("announcement has bad metric: %r"
                          % (ann.get("metric"),))
    try:
        ipaddress.IPv4Network(ann["subnet"])
    except ValueError:
        raise RouterError("announcement has bad subnet: %r"
                          % (ann.get("subnet"),))
    if seen_nonces is not None:
        seen_nonces.add(nonce)
    return {
        "hub_id": ann["hub_id"],
        "node_name": ann["node_name"],
        "subnet": ann["subnet"],
        "uplink_kind": ann["uplink_kind"],
        "metric": ann["metric"],
    }


def select_hub(announcements, key, want_uplink=True, seen_nonces=None,
               now=None):
    """Pick the best hub from raw announcements.

    Every candidate is verified first; anything stale, replayed,
    tampered, or foreign-signed is skipped and can NEVER be
    selected. With want_uplink, only hubs advertising a real uplink
    (kind != "none") qualify. Winner: lowest metric, ties broken by
    hub_id so the choice is deterministic. Returns the verified hub
    fields, or None when nothing qualifies."""
    verified = []
    for ann in announcements:
        try:
            verified.append(verify_announcement(
                key, ann, seen_nonces=seen_nonces, now=now))
        except RouterError:
            continue  # unverifiable: never selectable, by construction
    if want_uplink:
        verified = [h for h in verified if h["uplink_kind"] != "none"]
    if not verified:
        return None
    verified.sort(key=lambda h: (h["metric"], h["hub_id"]))
    return verified[0]


# ---------------------------------------------------------------------
# Chaining: who serves, who joins, at what metric
# ---------------------------------------------------------------------
def chain_plan(nodes):
    """Build the hub tree from node declarations.

    Each node: {"node_name", "uplink_kind", "uplink_iface" (roots),
    "via" (parent node_name or None), "serves" (bool)}.

    Roles:
      root-hub     own wifi/ethernet uplink, serves a PAN
      chained-hub  uplink is a PAN join to a parent hub ("pan" via),
                   and re-serves its own PAN at metric +10 per hop
      leaf         joins a hub's PAN, serves nothing
      standalone   own uplink, joins nothing, serves nothing
      isolated     no uplink, joins nothing

    hub_index is assigned root-hubs first (in input order), then
    chained hubs by (depth, input order), so plan_subnets() output
    is stable as the chain grows at the end. Returns entries sorted
    parents-before-children: {"node_name", "role", "depth",
    "metric" (hubs), "hub" (the make_hub record, hubs only),
    "via"}. Cycles and dangling "via" pointers raise RouterError.
    """
    by_name = {}
    for node in nodes:
        name = node.get("node_name")
        if not name or name in by_name:
            raise RouterError("node list has missing/duplicate "
                              "node_name: %r" % (name,))
        by_name[name] = node

    depth = {}

    def depth_of(name, trail):
        if name in depth:
            return depth[name]
        if name in trail:
            raise RouterError("cycle in chain via %s" % name)
        node = by_name[name]
        via = node.get("via")
        if via is None:
            depth[name] = 0
        else:
            if via not in by_name:
                raise RouterError("%s chains via unknown node %s"
                                  % (name, via))
            depth[name] = depth_of(via, trail | {name}) + 1
        return depth[name]

    entries = {}
    for name, node in by_name.items():
        d = depth_of(name, set())
        kind = node.get("uplink_kind", "none")
        via = node.get("via")
        serves = bool(node.get("serves"))
        if serves and via is None and kind in ("wifi", "ethernet"):
            role = "root-hub"
        elif serves and via is not None and kind == "pan":
            role = "chained-hub"
        elif serves:
            raise RouterError("%s: serves=True needs an uplink "
                              "(wifi/ethernet root, or pan via a "
                              "parent hub)" % name)
        elif via is not None:
            role = "leaf"
        elif kind in ("wifi", "ethernet"):
            role = "standalone"
        else:
            role = "isolated"
        if role in ("chained-hub", "leaf"):
            pnode = by_name[via]
            if not pnode.get("serves"):
                raise RouterError("%s chains via %s, which does not "
                                  "serve a PAN" % (name, via))
        entries[name] = {
            "node_name": name,
            "role": role,
            "depth": d,
            "via": via,
            "_uplink_kind": kind,
            "_uplink_iface": node.get("uplink_iface"),
            "_order": list(by_name).index(name),
        }

    hubs = [e for e in entries.values()
            if e["role"] in ("root-hub", "chained-hub")]
    hubs.sort(key=lambda e: (0 if e["role"] == "root-hub" else 1,
                             e["depth"], e["_order"]))
    for idx, entry in enumerate(hubs):
        metric = METRIC_PER_HOP * (entry["depth"] + 1)
        if entry["role"] == "root-hub":
            hub = make_hub(idx, entry["node_name"],
                           uplink_iface=entry["_uplink_iface"],
                           uplink_kind=entry["_uplink_kind"],
                           metric=metric, serve_iface="bnep0")
        else:
            # Chained hub: its client leg to the parent is bnep0;
            # it serves its own clients on bnep1.
            hub = make_hub(idx, entry["node_name"],
                           uplink_iface="bnep0", uplink_kind="pan",
                           metric=metric, serve_iface="bnep1")
        entry["hub"] = hub
        entry["metric"] = metric

    out = []
    for entry in entries.values():
        clean = {k: v for k, v in entry.items()
                 if not k.startswith("_")}
        out.append(clean)
    out.sort(key=lambda e: (e["depth"],
                            e["hub"]["hub_index"] if "hub" in e
                            else 1 << 30,
                            e["node_name"]))
    return out


# ---------------------------------------------------------------------
# Apply plan: renders as data, execution behind an arm
# ---------------------------------------------------------------------
def _step(node, kind, **fields):
    step = {"node": node, "step": kind}
    step.update(fields)
    return step


def render_plan(entries, bt_default=False):
    """Render an ordered command plan (DATA, nothing executes).

    entries: chain_plan() output. Order matters and is the point:
    a root hub stands up first; a chained hub joins its parent's
    PAN as a client BEFORE it starts serving its own; a leaf joins
    last. bt_default arms the Bluetooth default route on leaves
    (callers set it when the leaf's primary is down or an operator
    armed it -- see module docstring); without it, leaves get
    cluster routes only and their primary stays untouched.
    """
    by_name = {e["node_name"]: e for e in entries}
    steps = []
    for entry in entries:
        name = entry["node_name"]
        role = entry["role"]
        if role in ("root-hub", "chained-hub"):
            hub = entry["hub"]
            if role == "chained-hub":
                parent = by_name[entry["via"]]["hub"]
                steps.append(_step(
                    name, "panu-connect",
                    argv=["bt-network", "-c", "panu", entry["via"]],
                    note="join parent %s (%s); the on-box build "
                         "resolves the node name to its paired "
                         "BD_ADDR" % (parent["hub_id"],
                                      parent["node_name"])))
                steps.append(_step(
                    name, "await-iface", iface=hub["uplink_iface"],
                    note="proceed only when the BNEP client "
                         "interface is up"))
            steps.append(_step(name, "sysctl",
                               argv=render_ip_forward_cmd()))
            steps.append(_step(
                name, "nap-start",
                argv=["bt-network", "-s", "nap", hub["serve_iface"]],
                note="serve BNEP on %s, routed (never bridged)"
                     % hub["serve_iface"]))
            steps.append(_step(
                name, "addr-add",
                argv=["ip", "addr", "add", hub["address"] + "/24",
                      "dev", hub["serve_iface"]]))
            dnsmasq_path = "%s/dnsmasq-%s.conf" % (CONFIG_DIR,
                                                  hub["hub_id"])
            steps.append(_step(
                name, "dnsmasq", argv=["dnsmasq", "-C", dnsmasq_path],
                config_path=dnsmasq_path,
                config=render_dnsmasq(hub)))
            nft_path = "%s/nft-%s.nft" % (CONFIG_DIR, hub["hub_id"])
            steps.append(_step(
                name, "nft", argv=["nft", "-f", nft_path],
                config_path=nft_path, config=render_nft(hub)))
        elif role == "leaf":
            parent = by_name[entry["via"]]["hub"]
            steps.append(_step(
                name, "panu-connect",
                argv=["bt-network", "-c", "panu", entry["via"]],
                note="join %s (%s); name resolves to the paired "
                     "BD_ADDR on-box" % (parent["hub_id"],
                                         parent["node_name"])))
            steps.append(_step(
                name, "dhcp", argv=["dhcpcd", "bnep0"],
                note="lease + router option from the hub's dnsmasq"))
            for other in entries:
                if "hub" in other and \
                        other["hub"]["hub_id"] != parent["hub_id"]:
                    steps.append(_step(
                        name, "route-add",
                        argv=["ip", "route", "add",
                              other["hub"]["subnet"],
                              "via", parent["address"]],
                        note="cluster network of %s, reached via "
                             "the joined hub" % other["hub"]["hub_id"]))
            if bt_default:
                steps.append(_step(
                    name, "default-route",
                    argv=["ip", "route", "add", "default",
                          "via", parent["address"],
                          "metric", str(BT_DEFAULT_METRIC)],
                    note="armed by operator or primary-down; poor "
                         "metric so a returning primary wins"))
    for i, step in enumerate(steps):
        step["order"] = i
    return steps


class RouterArm:
    """Bounded arm for plan execution, mirroring
    ble_provision.ProvisioningWindow's discipline: disarmed by
    default, armed only by a local human act for a bounded time.
    Unlike the provisioning window it is NOT one-shot -- bringing a
    router up is a sequence of steps -- but it expires."""

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
            self._expires_at = None
            return False
        return True


def execute_plan(plan, armed=False, runner=None):
    """Execute a rendered plan, in order -- REFUSED unless armed.

    armed: True, or a RouterArm whose window is currently open
    (mirrors the provisioning arm discipline). Steps with a
    "config" payload have it written to their config_path before
    their argv runs. runner, when given, is called with each step
    dict instead of the default handling (tests inject it; the
    default is a thin subprocess runner). Returns the list of
    executed step kinds, in order."""
    if isinstance(armed, RouterArm):
        armed = armed.is_armed()
    if not armed:
        raise RouterError("plan execution refused: not armed")
    done = []
    for step in plan:
        if runner is not None:
            runner(step)
        else:
            if "config" in step:
                with open(step["config_path"], "w") as fh:
                    fh.write(step["config"])
            argv = step.get("argv")
            if argv:
                import subprocess  # lazy: rendering never needs it
                subprocess.run(argv, check=True)
        done.append(step["step"])
    return done
