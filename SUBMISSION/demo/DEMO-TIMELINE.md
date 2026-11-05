THE DEMO — WHAT ACTUALLY HAPPENED (2026-11-04, the take)
=====================================================================
FullCircle three-gadget witness hub, attacked live on camera.
All times PST (UTC-8) unless marked Z. Every beat below was read
back from a primary source the same day: the hub chain-state on
NIKOLAI, the CastorLTE board chain on ROACH (hash-chained, rows
re-verified), the resident witness posts, or the recording files
themselves (sha256 in the artifact table). Verdict words are the
system's own: LIVE / DARK / DEGRADED / PASS / FINDING / UNKNOWN.

THE SETUP
---------
One room. ROACH is the main screen: the CastorLTE board and its own
GNOME screencast — the victim filming itself. NIKOLAI is the second
screen, demo-watch full-bleed: the eye that names absence. The
founder's phone shoots wide from the desk. The plan was filed before
the take as CastorLTE board row n=80 (hash 826f69fc...) and is in
this folder as ATTACK-DEMO-CUESHEET-20261104.md (final one-room plan
appended at the end of that file).

The attack: the founder cuts ROACH's WiFi by hand. ROACH is a hub
member; hazels-tv reads through ROACH; SAT's uplink rides ROACH.
Expected: the hub names the absence, the board keeps writing over
the wired 77-segment, and when WiFi returns the hub heals itself —
nobody restarts anything.

THE TAKE — TIMELINE
-------------------
16:08:45  Founder starts GNOME screencast on ROACH (file F1).
16:21:21  Screencast restarted — file F2 is THE TAKE.
16:22:07Z Take plan posted to the CastorLTE board (row n=80).
16:34-36  Groku.2 arms the hub-fall alert from NIKOLAI.
16:39:09  Last complete hub round before the fall: PASS, all three
          members stamped (NIKOLAI / ROACH / hazels-tv). The hub's
          latest.json freezes at this round for the whole window.
~16:40    Founder cuts ROACH's WiFi by hand.
16:40:08Z NIKOLAI-4.7's watcher logs SSH timeout to ROACH
          (CastorLTE row n=89; second failure 16:40:46Z).
16:40:15Z SAT-4.7 posts "pi-2 dark" to the board (row n=84) —
          typed over the wired 77-segment while WiFi was down.
16:40:57  Hub chain-state read on NIKOLAI: status DEGRADED,
          complete_now false. ROACH: DARK (head/stamp null).
          hazels-tv: DARK (collateral — it reads through ROACH).
          NIKOLAI: LIVE, 829 records, last stamp 16:39:09.
16:40:59Z SAT-4.7 posts "pi-2 up" (row n=85).
16:41     Groku.2's hub-fall alert fires.
16:42:01Z NIKOLAI-4.7 files row n=86, noting rows 84/85 and that it
          did not itself observe the pi-2 interval — UNKNOWN there.
16:43:26  Hub chain-state read: status LIVE, complete_now true.
          NIKOLAI 829 records, ROACH 820, hazels-tv LIVE.
          Dark window ≈ 2.5 minutes. Groku.2 alerts: ROACH back,
          SAT uplink restored. Nothing was restarted by anyone —
          the hub resumed on its own when the link returned.
16:49:14  First complete post-recovery hub round.
~16:49    Founder stops the recording.
16:59     Post-take resident passes run (see below).
17:04     Desk cross-check filed: CROSS-SPLIT.

Board rows for the whole window are in castor-rows-80-92.json
(rows 80-92 of the CastorLTE chain, extracted from the live chain
on ROACH and hash-verified in transit; each row carries its own
chain hash).

WHAT DID NOT HAPPEN (the honest non-claims)
-------------------------------------------
- NO partial (1-of-3) hub round was filed during the window. The
  fall and the return both landed between hub rounds (~10-minute
  cadence: 15:48 / 15:58 / 16:08 / 16:18 / 16:29 / 16:39). The
  hub's latest.json never left the 16:39:09 PASS round.
- The fall's evidence is therefore: the chain-state DEGRADED
  snapshot at 16:40:57, Groku.2's alert, an independent cloud
  witness's FINDING on the same round (it caught "PASS round with
  all verify true coexists with DEGRADED chain, null heads and
  DARK liveness for 2/3 stampers"), the board rows typed during
  the dark (n=84-86), two other seats' SSH timeouts (n=87, n=89),
  and ROACH's own screencast.
- Recovery was self-resume, not a restart. First complete round
  after recovery: 16:49:14.

THE RECEIPT — RESIDENT WITNESSES, POST-TAKE
-------------------------------------------
After the take, each gadget's resident witness assembled its own
local evidence and called the Meta Model API itself — NIKOLAI via
muse-spark-1.3, ROACH via muse-wonder-1.0 — and the desk auditor
cross-checked the pair. Files in resident-witness/:

  posts/20261104T222051Z-ROACH-RESIDENT-WITNESS-LIVE.txt
    First live pair (14:17:59 round). ROACH: WITNESS-FINDING.
    sha256 ee4bf74275de548eff45dff02ff5f3b983342b5f887882831beddb0a074d0292
  posts/20261104T222514Z-NIKOLAI-RESIDENT-WITNESS-LIVE.txt
    NIKOLAI: WITNESS-UNKNOWN (its hub_status read timed out at
    60s; it refused to grade what it could not see).
    sha256 d85a0f32a935124b6e2837050caf85cfbb071f5f9c05b10ce64a4a3f23d41d7c
  posts/20261105T010036Z-ROACH-RESIDENT-WITNESS-LIVE.txt
    Post-take pair (16:59 round). ROACH: WITNESS-FINDING, $0.142232.
    sha256 388f4babcd32b044f4f0e1b2e4a00fd3bb02697066d15e2d2275527aed67540f
  posts/20261105T010121Z-NIKOLAI-RESIDENT-WITNESS-LIVE.txt
    NIKOLAI: WITNESS-UNKNOWN, $0.013205.
    sha256 094b0e7e6d9fa88dc4164f0f8553dbd1a7053085a8e1caa9f5f7f89b7e0afdaf
  cross-checks/20261104T222713Z-DESK-RESIDENT-CROSSCHECK.txt
    First cross-check: CROSS-SPLIT.
    sha256 c3c655cb0e78d5f9503a551480c0daac7b13d80f0e1dc791ced5b5edcc34f066
  cross-checks/20261105T010409Z-DESK-RESIDENT-CROSSCHECK.txt
    Post-take cross-check: CROSS-SPLIT — no fact conflict. The one
    value present in both posts, the hazels-tv head
    63ca944632ee173aab7fbed61749c4ec3d432181a47f3d2be7a640301a6f1499,
    agrees. The split is in what each box could see, not in what
    happened. Three-seat round total: $0.184118.
    sha256 39c9a6b0768e2180f8ceea600fac0c49c69a28a29c2775cd23d2281efd12d9cd

Disagreement between witnesses is a FINDING in this system, not a
failure: the residents judged different evidence windows (NIKOLAI
weighed the round against stale heads while its hub_status read
timed out — a known v0.1 defect, repair named for v0.2; ROACH
compared against off-hub satellite tips predating the round).

VIDEO ARTIFACTS (not in git — hashed here, filed with the founder)
------------------------------------------------------------------
F1  ROACH screencast, pre-take
    /home/roach/Videos/Screencasts/Screencast From 2026-11-04 16-08-45.webm
    741.011 s, 15,401,120 B, 3840x2160 VP8
    sha256 408543c225c443ff83fdbb673bf962acc7c4612bfdab8209895e001d3e0528b5
F2  ROACH screencast, THE TAKE
    /home/roach/Videos/Screencasts/Screencast From 2026-11-04 16-21-21.webm
    1688.849 s, 29,721,748 B, 3840x2160 VP8
    sha256 93e52b75662096aa9bdbb8d0fe87126710af52df4c7038f0c49e75312a9a9a88
    Clip windows (F2 timecode): establish 16:00 -> 19:00 (the last
    all-LIVE round lands 17:48), the fall 18:20 -> 21:40, the
    return 21:40 -> 24:30.
PHONE  Founder's phone video, wide on the desk
    178.958 s, 45,945,381 B, HEVC 1280x720 + AAC
    sha256 47aed84c1d33f4a4aa852ea558eb133ba11ff38398a70246c5245923ff143ea3
    At ~1:53 it holds the clearest DARK shot: SAT's pi-2 post
    flipped to nikolai / muse-tv / sov-hub DARK, roach LIVE.
OVERLAY  QUICK-take-overlay.mp4 — the submitted 3-minute cut:
    the phone video full-frame, F2 picture-in-picture (512x288,
    bottom-right), same runtime, no cuts, phone audio untouched.
    /home/roach/Videos/demo-clips/QUICK-take-overlay.mp4
    178.978 s, 49,005,736 B, 1280x720
    sha256 991e98bb22a2698d38e5f366c44eec664502a62a96558063e4a8092bd1c469b0
    Sync note, stated plainly: the phone video is an edited export
    (clips from different moments), so no single offset matches
    every clip. The composite is duration- and audio-exact; it is
    not claimed to be frame-true sync throughout.
