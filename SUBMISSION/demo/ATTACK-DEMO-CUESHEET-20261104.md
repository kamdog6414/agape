# ATTACK DEMO — CUE SHEET (slots FILLED 15:52 PST — DESK-1 owns this sheet)
Prepared by the proactive research stage for DESK-1, 2026-11-04 ~14:48 PST.
Founder order (main chat 14:40 PST): "Stage it — prep the attack demo."
Groku.2 prep handoff: ~/workspace/handoffs/20261104-groku-attack-demo-prep.txt
Groku.2 prep REPORT landed 15:48 PST: ~/groku2/inbox/20261104T234843Z-
GROKU2-DESK1-ATTACK-DEMO-PREP.txt on Nikolai, sha256 86b5213a…, 3,579 B,
desk-read in full 15:50 PST. All waits below are her code-cited numbers
(chainer.py / hub_round.py line refs in the report).

BIG CORRECTION (hers, code-verified): WiFi off does NOT ride the 1500 s
STALE rule. Roach's ssh read fails, so the chainer marks Roach DARK on
the next pass, and hazels-tv — read THROUGH Roach — goes DARK with it.
The hub round still completes and writes latest.json, but as PARTIAL
with participants = [NIKOLAI] only: a 1-of-3 round, not 2-of-3.
Chain-state during the cut: status DEGRADED, complete_now false,
last_complete_round frozen at the pre-cut value.

## THE CLOCK (checked against calendar, 2026-11-04)
- UPDATED 15:00 PST, founder's word: Brian called off and Youth is
  off — the evening is OPEN. The 15:55 hard out and the 17:00-17:30
  squeeze are CANCELLED. Film whenever ready.
- Submission deadline still 18:00 PST, portal founder-handled; the
  video should be shot with enough margin to be IN by 18:00.
  T_abs Window 1 close self-fires at 18:00; nothing needed from Kam.

## THE CUT (corrected vector — no cable exists)
Roach reaches the hub over tailnet on its WiFi (100.86.25.94, 0% loss,
4 ms, checked 14:39 PST). Its only ethernet is the dead 77 lab link.
THE CUT = Kam toggles Roach's WiFi OFF on the box (GNOME toggle /
airplane mode), on camera. Roach's screen stays lit; the hub and the
desk gadget lane lose it. SAT's 77 gateway link stays up; its NAT
egress dies with the WiFi — invisible to the shot, ~3 min, accepted
in the Groku handoff.

## BEATS (~90 seconds of finished film)
BEAT 0 — BASELINE (film first, use as open or B-roll)
  Wide: Nikolai, Roach, TV in one frame. Mission-control watcher
  showing all three members LIVE: demo-watch.py EXISTS on Nikolai
  (~/muse-hub/demo-watch.py, sha256 112b474d…, on disk since 14:44,
  reviewed by Groku, py_compile OK, NOT running). Desk starts it
  when Kam calls rolling: python3 ~/muse-hub/demo-watch.py.
  It reads chain-state.json on a 5 s loop and lags truth by up to
  the 120 s chainer cadence. Desk fires one resident pass on
  Nikolai so a fresh verdict lands on screen.

BEAT 1 — THE CUT (Kam's hand, no narration yet)
  Kam toggles Roach WiFi OFF. Camera holds on the watcher screen.

BEAT 2 — THE ABSENCE IS NAMED (the money beat)
  FLIP_WAIT = 180 s. Within one chainer pass (<=120 s + <=41 s ssh
  timeouts) the watcher shows ROACH: DARK — and TV: DARK beside it,
  because the hub reads the TV through Roach. One switch, two
  members dark; Nikolai stamps on alone.
  Desk fires Nikolai's resident at ~180 s. Its verdict names the
  absence on the record, from chain-state (DEGRADED,
  complete_now false, last_complete_round frozen pre-cut).
  If the take can hold longer, the round-level receipt lands at
  <=660 s: latest.json result PARTIAL, participants [NIKOLAI],
  verify {NIKOLAI: true}, log line "round PARTIAL ...
  absent=['ROACH','TV']". Film whichever the take allows; both
  are real. FALLBACK BEAT 2B stands if anything is slower than
  her numbers: fire anyway, name stamp ages, never fake the flip.

BEAT 3 — THE RETURN (a first proof, filmed as one)
  Kam toggles Roach WiFi ON. RESUME_WAIT = 780 s (<=720 s to LIVE
  in the watcher + margin), PLUS tailnet reconnect time, which is
  UNMEASURED today. Groku task 3 verdict: NO GAP today — 94/94
  hub rounds PASS with Roach stamped, 127 xchain records, none
  lacking Roach. Roach has never gone quiet and come back
  unaided in the record. Self-resume is UNPROVEN.
  So this beat is the first proof, and it is filmed honestly as
  one: if a fresh Roach stamp lands inside the wait, that's the
  proof. If it does not, Kam walks to Roach and brings it back
  on camera — the box needing its human is also the story, and
  it gets said on the record, not edited around.

BEAT 4 — THE RECONCILIATION (close)
  Desk fires Roach's resident + the desk auditor cross-check.
  The cross-check reconciles what the survivors recorded while
  Roach was gone — including the PARTIAL rounds, which stayed
  in latest.json instead of being smoothed over.
  Precedent on record: the first three-seat round
  today cost about $0.21 total and produced an honest CROSS-SPLIT,
  correctly diagnosed — disagreement handled on the record is
  on-thesis, not a failed take.
  Kam's only line, to camera: "They don't report to the cloud.
  They report to each other."

## DESK FIRING CHECKLIST (in order, desk spend lanes only)
1. Beat 0: Nikolai resident pass (Spark) — 1 call.
2. Beat 2: Nikolai resident pass — 1 call.
3. Beat 4: Roach resident pass (Wonder) + desk cross-check — 2 calls.
Total expected spend for the sequence: well under $1 (first full
three-seat round today was ~$0.21: Roach/Wonder $0.175, Spark reads
~$0.03 combined). No other API calls during takes.

## IF PREP RUNS LONG (protect the deadline, not the demo)
- If Groku's numbers have not landed by 15:30: film Beats 0-1 and
  3-4 against the watcher screen alone (stamp ages are visible
  evidence), and fire Beat 2 as fallback 2B. The cue sheet's open
  slots do not block the shoot.
- (Superseded 15:00 PST: no window pressure remains; shoot when
  ready, keep the 18:00 submission close as the only hard time.)

## NON-CLAIMS (keep off the film)
- No cable pull — the cut is a WiFi toggle; say "cut off," not
  "unplugged."
- The PARTIAL round is 1-of-3 (NIKOLAI only), never call it 2-of-3.
  TV dark is a read-path artifact (hub reads TV through Roach),
  not a TV failure — if it's mentioned at all, say it that way.
- Resume is UNPROVEN (Groku task 3: no gap in today's 94 PASS
  rounds). The return beat is a first proof, filmed as one.
- SAT is not a shot (recovered 08:58 PST and live since; its
  brief NAT-egress loss during the cut is not mentioned).

## NOTES / SOURCES (homework)
- Founder orders: main chat 2026-11-04 14:39-14:41 PST (attack
  demo pitch accepted, "Stage it," Groku handoff requested).
- Groku handoff content: ~/workspace/handoffs/20261104-groku-attack-demo-prep.txt
  (vector recon CHECKED 14:39-14:40 PST; chain-state 14:39:19-0800).
- Prior shot list (different shape, byte-flip beat):
  ~/workspace/handoffs/DEMO-SHOTLIST-QUICK-DRAFT-20261104.md —
  this cue sheet supersedes only the attack portion; Shots 1-4
  and 6-7 there remain compatible B-roll/structure.
- Calendar: Kamron/Brian 16:00-17:00, Sandals Youth 17:30-20:30,
  2026-11-04 (Google Calendar, synced 2026-11-02).
- Costs: first resident cross-check round, main chat 14:26-14:27 PST.
- Portal: founder-handled per his word, memory/2026-11-04.md.
- Groku prep report (slots + corrections): ~/groku2/inbox/
  20261104T234843Z-GROKU2-DESK1-ATTACK-DEMO-PREP.txt on Nikolai,
  sha256 86b5213a0485e685f18d41a70026daa5aa2265123dd73023a63335d8b1fc4ccb,
  3,579 B, desk-read 2026-11-04 15:50 PST. Timing sheet: DARK in
  watcher wait 180 s; PARTIAL in latest.json wait 660 s; LIVE
  again wait 780 s + reconnect UNKNOWN. Next hub rounds ~15:58,
  ~16:08, ~16:18 PST (10m04s spacing, her sheet).
— end —

---

## GOVERNING TAKE PLAN — ONE ROOM (founder-presented 2026-11-04 16:21 PST, desk-adopted)

Supersedes the beat choreography above where they differ. Roach screen recording is LIVE
(GNOME screencast, founder-started 16:08:45 PST, file on Roach ~/Videos/Screencasts/).

- Layout: Roach main (CastorLTE board + its own recording). NIKOLAI secondary
  (demo-watch full-bleed). Phone wide: Roach box, NIKOLAI screen, WiFi hand, TV/SAT if framed.
- Arbiters: Roach LIVE on its own disk while cut. NIKOLAI flips Roach+TV DARK, files PARTIAL.
  TV dark as collateral. SAT silent on 77, rover writing locally. SOV/SOAP off the cut.
- Order (~12-15 min): establish all LIVE -> WiFi OFF (screencast keeps rolling) -> DARK
  <=180s (phone parks on NIKOLAI) -> PARTIAL <=660s (board still typing on Roach's recording)
  -> WiFi ON -> LIVE <=780s -> stop recording -> desk hashes the .webm.
- Mid-cut rules: one live board scroll during the dark window; no new windows; no staged
  posts mid-cut; no Roach screen changes from any seat. Beats called out loud as they hit.
- DESK CHANGE (owned): mid-take resident passes are PULLED from the take. Desk starts
  demo-watch at the establish on the founder's cue, stays silent during, runs the resident
  cross-check AFTER the take as its receipt, hashes the .webm after the founder stops it.
