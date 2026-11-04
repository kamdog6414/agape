#!/usr/bin/env python3
"""one-shot, idempotent: append seed SCORE/OBS records (real completed jobs) to calibration.jsonl. Never rewrites lines."""
import os, sys, json
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import learn
d = json.load(open(os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else "seed-20261104.json")))
for s in d["scores"]: learn.score(s["fc"], s["fin"], s["kind"], s["node"], source=s["source"])
for o in d["obs"]: learn.observe(o["node"], o["kind"], o["job"], o["start"], o["fin"], o["total"], o["unit"], o["source"], note=o.get("note"))
learn.calibrate_all(os.environ.get("ETA_NODE"))
learn.report()
