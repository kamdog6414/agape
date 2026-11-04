#!/bin/bash
# Tests for xchain.py baseline (works on temp copies only)
X=/workspace/xchain-v1/xchain.py; SRC=/workspace/xchain; T=$(mktemp -d); pass=0; fail=0
setup(){ rm -rf $T/*; mkdir -p $T/p; cp $SRC/peers/*.jsonl $T/p/; cp $SRC/baselines/BASELINE-atom.json* $T/; }
run(){ python3 -B $X baseline --manifest $T/BASELINE-atom.json --peers-dir $T/p; }
chk(){ if [ "$1" = "$2" ]; then echo "PASS: $3"; pass=$((pass+1)); else echo "FAIL: $3 (rc=$1 want $2)"; fail=$((fail+1)); fi; }
setup; run >/dev/null; chk $? 0 "unchanged+appended passes"
setup; python3 - $T/p/ROACH.jsonl <<'P'
import sys,json;f=sys.argv[1];L=open(f).read().splitlines();r=json.loads(L[50]);r["self_head"]="tampered";L[50]=json.dumps(r,sort_keys=True,separators=(",",":"));open(f,"w").write("\n".join(L)+"\n")
P
o=$(run); rc=$?; echo "$o"|grep -q "ROACH: ATOM BROKEN (hash mismatch at 50)"; chk "$rc$?" 10 "edited pre-atom record fails"
setup; head -n 100 $T/p/NIKOLAI.jsonl > $T/x && mv $T/x $T/p/NIKOLAI.jsonl
o=$(run); rc=$?; echo "$o"|grep -q "NIKOLAI: ATOM BROKEN (truncated"; chk "$rc$?" 10 "truncated chain fails"
setup; sed -i 's/"records": 80/"records": 79/' $T/BASELINE-atom.json
o=$(run); rc=$?; echo "$o"|grep -q "ATOM MANIFEST BROKEN"; chk "$rc$?" 10 "tampered manifest fails"
setup; rm $T/p/TV.jsonl; o=$(run); rc=$?; echo "$o"|grep -q "TV: ATOM UNKNOWN"; chk "$rc$?" 00 "missing chain -> UNKNOWN (not broken)"
rm -rf $T; echo "tests: $pass pass, $fail fail"; [ $fail = 0 ]
