# Agape as a Bluetooth hub — full IP networking over Bluetooth PAN

Bluetooth in Agape is not just messaging. Provisioning hands a node
its config (BLE.md, Role 2); the PAN carries signed envelopes between
two linked nodes (BLE.md, Role 1). This is the third role: a hub
SHARES its internet connection over Bluetooth, the way a phone
hotspot shares its radio. A node with a working WiFi or Ethernet
uplink serves a Bluetooth PAN, NATs its clients out through that
uplink, and clients get real IP networking — WiFi sharing included —
with no router, no cable, and no infrastructure at all.

Reference implementation: `bt_router.py` (topology, address plan,
config renders, signed announcements, chaining, armed apply plan —
hardware-free, stdlib only) + `test_bt_router.py`. As with the rest
of fc-link, the core is the protocol; the on-box BlueZ/dnsmasq/nft
wiring is a later build. Nothing in this file is live yet: live
bring-up is an operator ceremony per box, on the founder's go.

## The chaining model — Agape is the hub protocol

One-off PAN links don't scale and don't fail gracefully. Agape makes
hub-and-chain the protocol:

- **Hubs announce, signed.** A hub broadcasts an announcement —
  `{v, kind, hub_id, node_name, subnet, uplink_kind, metric, ts,
  nonce, sig}` — HMAC-SHA256 over canonical JSON with the cluster
  FC-Link key, the exact scheme `ble_provision.py` already uses
  (imported, not re-implemented). Verification is constant-time,
  timestamps must sit within 300 s, nonces are single-use.
- **Clients choose, verified.** A joining node verifies every
  announcement it hears and picks the lowest-metric hub *with an
  uplink*. Anything stale, replayed, tampered, or foreign-signed is
  skipped and can never be selected — a forged "metric 0, trust me"
  announcement fails its signature and is invisible to selection.
- **Clients can re-serve.** A node whose only uplink is a PAN join
  to a parent hub can itself become a hub for the next ring out:
  leaf → hub → hub → internet. Its metric is its parent's +10 per
  hop, and it serves the next subnet in the plan. The chain is a
  tree computed by `chain_plan()` — cycles, dangling parents, and
  chaining through a node that doesn't serve are all refused at
  plan time, before anything touches a radio.

## The address plan

Deterministic, collision-free, and stable as the chain grows:

- hub-0 keeps the fleet's existing PAN subnet, **192.168.79.0/24** —
  Nikolai already holds 192.168.79.1 there (see below). Nothing
  renumbers.
- Hub index *i* serves **192.168.(79+i).0/24**; the hub is always
  `.1` in its own subnet and hands out `.10`–`.200` by DHCP.
- Indices are assigned root hubs first, then chained hubs by depth.
  Appending a hub at the end never changes an existing assignment,
  and a hub record whose declared subnet disagrees with the plan is
  refused rather than renumbered.

## Routed, never bridged

Each hub routes between its PAN interface and its uplink; it never
bridges them. Bridging chained PANs would merge broadcast domains
across a tree whose shape changes as nodes join, leave, and lose
power — spanning tree over intermittently present BNEP links is a
loop generator. Routed hops keep every PAN an independent failure
domain, make per-hub DHCP and the address plan above possible, and
give the firewall a clean edge to police.

That edge is fail-closed. The rendered nftables ruleset:

- masquerades **only** on the uplink interface;
- forwards PAN → uplink, and uplink → PAN only for
  established/related return traffic;
- drops everything else (chain policy drop). A hub with no uplink
  renders no NAT and no forwarding accepts at all — it can serve
  its own PAN locally and forwards nothing anywhere.

Enabling IP forwarding itself is a rendered command in the plan —
never a silent side effect of importing or planning.

**Metric discipline.** A client joining a hub always installs
routes to the cluster's other served subnets. It installs the
*default* route via Bluetooth only when its own primary is down or
an operator armed it — and even then at metric 600, so the moment a
real primary returns, it wins. Bluetooth fills gaps; it does not
silently hijack a working link.

## Honest physics

BNEP on these radios is a ~1–3 Mbps class link in the real world.
That is the right size for what the cluster actually moves between
boxes day to day: FC-Link command traffic, xchain rounds and
witnessing, telemetry, hub announcements, enrollment. It is the
wrong size for bulk — multi-MB file transfer, chain sync of large
ledgers, and media stay on cable / WiFi / tailnet whenever those
exist. The Bluetooth router is the network that is *always there*,
including when the infrastructure is gone; it is not a WiFi-speed
replacement and doesn't pretend to be.

Range is room-scale per hop (~10 m class) — which is exactly why
chaining is the design: each hop is short, and the tree walks the
network across a house or a site one room at a time.

## Platform map

- **Linux boxes (Nikolai, Roach, JUPI)** can run BlueZ BNEP in NAP
  (hub) or PANU (client) role today. `bt_router.py` targets them.
- **SOV participates via its Windows-hosted PAN.** SOV's Bluetooth
  PAN has always been terminated by the Windows Bluetooth stack —
  the 192.168.79.x link from the fclink-bt era is a Windows PAN
  presence, and WSL cannot own BNEP. So SOV is modeled as a PAN
  participant at its Windows address; this module claims no WSL
  hub role for it. A SOV hub, if ever wanted, is a Windows-side
  configuration and a separate build.

## Where this starts from: the live fact

This is a generalization, not a green field. Nikolai already holds
192.168.79.1/24 on its Bluetooth PAN interface today, with
`fclink-bt.service` keeping the PAN link up and FC-Link bound to the
address (IP_FREEBIND, so the bind survives the link being down).
That one-off leg — one hub, one subnet, one peer — is hub-0 of the
address plan. `bt_router.py` turns it into the Agape function: any
Linux node can be hub-*n*, announcements make hubs discoverable
instead of hand-configured, and chaining replaces the single link
with a tree.

## Bring-up ceremony (future work — founder's go, per box)

Live application is deliberately NOT part of the module. When the
founder calls it, per box, the shape is:

1. On the hub box, render the plan (`render_plan`) and read it —
   every command, config file, and rule is visible before anything
   runs.
2. Arm the executor on the hub (local act, bounded window — the
   `RouterArm` in `bt_router.py`, same discipline as the
   provisioning window) and apply. The hub starts its NAP, takes
   its `.1`, serves DHCP, installs its nftables ruleset.
3. On the client, join the PAN (PANU), take the lease. Verify with
   a **signed FC-Link health call over the Bluetooth route** — the
   same envelope discipline as every other transport; a route that
   can't carry a verified health call isn't up, whatever the link
   light says.
4. A client that will re-serve repeats steps 1–3 as a chained hub:
   join parent first, then serve.

One box at a time, receipts at each step, and the existing
hand-kept PAN leg on Nikolai is migrated — never silently
replaced — when its turn comes.
