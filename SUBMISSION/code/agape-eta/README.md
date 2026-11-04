# agape-eta — realistic ETA from real-work units (ADDITIVE, not wired)
Beside the T_abs clock (~/fullcircle/tabs/window1), touches nothing of it.
  python3 eta.py watch <log> --unit articles --total 8516991 --job wikidb [--at "2026-11-04 09:00"] [--no-record]
  python3 eta.py score --job wikidb --finished "YYYY-MM-DD HH:MM:SS"
  python3 eta.py report
Rate = last --window-min (15) of samples; P10/P90 from per-interval rate spread + overall rate. forecasts.jsonl / scores.jsonl are sha256 hash-chained (prev+record).
Rollback: rm -rf ~/agape-eta

## eta top (live view, added 2026-11-04)
  cd ~/agape-eta && python3 top.py            # live, refresh 1s, Ctrl-C quits; B/W ANSI, read-only
  python3 top.py --once                       # one frame (2 samples 1s apart)
  python3 top.py --file PATH:TOTALBYTES[:NAME] # also track a growing file by size
  ./top_sat.sh TOTALBYTES                     # SAT wikidb file over ssh — needs a route to "sat" (none from NIKOLAI as of 2026-11-04)
Rate = top.py own samples over last 30s (shows -- until 2 samples). Countdowns tick from absolute eta_p10/50/90 in status/peers json. Never writes ledgers.

## self-learning (added 2026-11-04 10:45 PST, learn.py)
Every 5-min run: DONE jobs -> every forecast for that job scored (idempotent by forecast hash) into scores.jsonl and calibration.jsonl;
per cal_kind median P50 error, spread, coverage; next forecasts shifted/widened (raw_p* kept in forecasts.jsonl);
OBS throughput priors per node+kind give a first-sample ETA for kind=file/process. calibration.jsonl uses the FAILS-LEDGER
hash convention (canonical JSON, prev_hash/hash, seq); each record is a claim + falsifier, verdict 0 HOLDS / 1 FAIL / 2 UNKNOWN.
  python3 learn.py          # calibration report      python3 learn.py verify
