"""Satellite timer entry: scan ./inbox, write ./verdicts/<bundle>.json, chain ./agape-verdicts.jsonl.
Usage: agape_verify_scan.py VERIFIER_NAME   (separate from the XCHAIN satellite; touches only this folder)"""
import os, sys
sys.dont_write_bytecode = True
H = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0], "--scan", os.path.join(H, "inbox"), "--outdir", os.path.join(H, "verdicts"),
            "--verifier", sys.argv[1] if len(sys.argv) > 1 else "UNKNOWN", "--chain", os.path.join(H, "agape-verdicts.jsonl")]
sys.path.insert(0, H)
import verify_receipt
verify_receipt.main()
