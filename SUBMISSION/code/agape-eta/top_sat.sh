#!/bin/bash
# eta top against SAT's growing wikidb file, sampled over SSH.
# Usage: ./top_sat.sh TOTALBYTES     (expected final size; UNKNOWN by default - you must supply it)
# Requires an existing ssh route to host alias "sat". As of 2026-11-04 10:4x PST NIKOLAI had NO route
# (ssh sat -> "No route to host"). No keys are added by this script.
T=${1:?usage: top_sat.sh EXPECTED_TOTAL_BYTES}
F='~/fieldkit/wikidb/wiki-roach-20261104-1016.db'
cd "$(dirname "$0")" && exec python3 top.py --remote-file "ssh -o BatchMode=yes -o ConnectTimeout=5 sat stat -c %s $F|$F:$T:sat-wikidb"
