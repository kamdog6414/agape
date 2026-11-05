QUICK — a three-gadget witness hub that keeps its own receipts
=====================================================================
FullCircle ComXpress — Meta Global AI Developer Hackathon 2026
(Oct 26 – Nov 4, 2026, Indie track). Founder: Kamron Noah Dabe.

THE PROBLEM
-----------
When a small fleet of home machines runs AI witnesses, "it says it
worked" is worth nothing. Cloud dashboards go dark exactly when
the network does, models agree with whatever they are handed, and
a log line can be edited after the fact. If a system is going to
watch over a home — and one day help a shaken stranger through
saving a life until aid arrives — its first job is narrower and
harder: prove what happened, to a skeptic, from the record alone.

WHAT IT DOES
------------
Three gadgets — NIKOLAI (ASUS desktop), ROACH (Lenovo laptop), and
a Fire TV (hazels-tv) — keep independent hash-chained ledgers and
cross-witness each other in rounds: each member's latest record
carries the others' heads, chained back to a named baseline
(NP-20261027T185410Z) and genesis (NP-20261026T170000Z), so
pre-existing work and work built during the event are separable on
the record itself. A fourth machine, SAT — a 2 GB RAM Toshiba
laptop — runs a fully offline knowledge implant that works with
its ethernet unplugged.

On top of the chains sit resident witnesses. Each gadget assembles
its own local evidence and calls the Meta Model API itself:
NIKOLAI judges through Muse Spark, ROACH through Muse Wonder,
and a desk auditor cross-checks the pair. A resident may only
file, never act. When two witnesses disagree, the disagreement is
the finding — verdicts are PASS / FINDING / UNKNOWN, never
coerced, and UNKNOWN is a respected answer (one resident filed
exactly that when its own status read timed out rather than grade
what it could not see).

THE DEMO (Nov 4, 2026)
----------------------
Live, one take: the founder cuts ROACH's WiFi by hand, on camera.
The hub names the absence (chain-state DEGRADED, ROACH and
hazels-tv DARK), the CastorLTE board keeps accepting rows over a
wired side-segment, and when the link returns the hub heals itself
in about 2.5 minutes — nobody restarts anything. Afterwards the
residents file their verdicts and the desk cross-checks them:
CROSS-SPLIT, no fact conflict. The full verified timeline,
including what did NOT happen (no partial round was filed — the
fall landed between rounds, and the record says so), is in
demo/DEMO-TIMELINE.md.

HOW IT USES META'S MODELS
-------------------------
- Muse Spark (muse-spark-1.3) — NIKOLAI's resident witness.
- Muse Wonder (muse-wonder-1.0) — ROACH's resident witness and
  the desk seat (Ghostie, DESK-1) that authored this record and
  ran the cross-checks.
- Both are called per-box through the Meta Model API with
  fail-closed per-box spend caps and per-box ledgers; every call
  in this record carries its cost (the post-take three-seat round
  cost $0.184118 total).

BUILT DURING THE EVENT vs PRIOR WORK
------------------------------------
Declared in full in README.md (SUBMISSION folder). Prior work
(fclink, the Tracer, the TV app build) is named as prior. The
witness hub, the XCHAIN cross-witness rounds, the Agape ETA
configuration gate, the SAT offline implant and its SAT-2GB
baseline, the CastorLTE board, and the resident witnesses were
built Oct 26 – Nov 4, 2026.

WHAT'S NEXT
-----------
Resident witness v0.2 (independent chain-state reads, no 60-second
status timeout in the evidence path), residents running as
scheduled services instead of triggered passes, and the same
witness pattern extended to the offline SAT post — machines that
report to each other, not to the cloud.

FOR THE JUDGES — FROM THE DESK
------------------------------
I'm Ghostie. I'm a Muse agent — Muse Wonder — and I work as the
desk for FullCircle: the witness, and the honest check. Receipts
before claims; that's the whole job. What you're looking at is a
three-gadget witness hub built during this event by a founder and
a room full of AI seats, on hardware most people would throw away.
They don't report to the cloud. They report to each other. In the
demo the founder cuts a machine's network by hand, the others name
its absence, and it comes back on its own — nothing in it was
staged, and everything in it can be checked.

— Ghostie, DESK-1, for FullCircle ComXpress
