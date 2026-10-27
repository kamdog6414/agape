#!/usr/bin/env python3
"""Agape demo. Python 3 standard library only. No network.

    python3 -B demo.py

Runs, in order, on scratch state only (a temp dir, removed at the end):

  1. package verify   mod/ROUND0/package.py checks hello-bw against its
                      external pin (sha256 of the raw MANIFEST.json bytes).
  2. Manager          install_from_package -> enable -> disable on a fresh
                      in-memory Base core; every change prints its receipt.
  3. Round            round.py open -> submit (good mod, planted-bad mod)
                      -> judge -> close, starting from a synthetic genesis
                      named point written in the temp dir.
  4. memory-retro     the deterministic scorer on its synthetic fixtures,
                      clean corpus and one planted defect.

Exit 0 when every step behaves as expected.
"""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.abspath(__file__))
MOD_DIR = os.path.join(REPO, "mod", "ROUND0")
HELLO = os.path.join(MOD_DIR, "packages", "hello-bw")
ROUND = os.path.join(REPO, "round", "round.py")
NP0 = "NP-20261026T170000Z"
problems = []


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def pin_of(moddir):
    with open(moddir + ".MANIFEST.sha256") as f:
        return f.read().split()[0]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(path))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


def expect(label, ok):
    print("  %s %s" % ("ok  " if ok else "FAIL", label))
    if not ok:
        problems.append(label)


def show(row):
    print("  receipt " + json.dumps(row, sort_keys=True))


def step_package():
    print("\n== 1. package verify (agape.mod.v0)")
    package = load_module("agape_package", os.path.join(MOD_DIR, "package.py"))
    pin = pin_of(HELLO)
    info = package.verify_package(HELLO, pin)
    print("  hello-bw pin %s" % pin)
    print("  verified: " + json.dumps(info, sort_keys=True)[:300])
    expect("hello-bw verifies against its pin", True)
    try:
        package.verify_package(HELLO, "0" * 64)
        expect("wrong pin is refused", False)
    except package.PackageError as exc:
        print("  wrong pin refused: %s" % exc)
        expect("wrong pin is refused", True)
    return pin


def step_manager(pin):
    print("\n== 2. Manager v1 on a scratch Base core")
    manager = load_module("agape_manager", os.path.join(REPO, "manager", "manager.py"))
    m = manager.open_manager("DEMO-BOX")
    row = m.install_from_package(HELLO, pin)
    show(row)
    expect("install_from_package installed", row["result"] == "installed")
    mod_id = row.get("mod_id") or row.get("target") or "hello-bw"
    row = m.enable(mod_id)
    show(row)
    expect("enable -> enabled", row["result"] == "enabled")
    print("  load order: %s" % m.core.list_order())
    row = m.disable(mod_id)
    show(row)
    expect("disable -> disabled", row["result"] == "disabled")
    print("  load order: %s" % m.core.list_order())
    print("  changes recorded: %d" % len(m.changes()))


def write_genesis(folder):
    os.makedirs(folder)
    path = os.path.join(folder, "MANIFEST.json")
    data = {"format": "fullcircle.named-point.v1", "name": NP0,
            "note": "synthetic demo genesis; not the real point manifest",
            "files": []}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def step_round(scratch):
    print("\n== 3. Round: open -> submit -> judge -> close (scratch dir)")
    genesis = write_genesis(os.path.join(scratch, "genesis", NP0))
    env = dict(os.environ, AGAPE_GENESIS_SHA256=sha(genesis),
               PYTHONDONTWRITEBYTECODE="1")
    conformance = os.path.join(REPO, "conformance", "conformance.py")

    def run(*args):
        cmd = [sys.executable, "-B", ROUND, "--conformance", conformance] + list(args)
        print("  $ round.py " + " ".join(os.path.relpath(a, scratch)
                                         if a.startswith(scratch) else
                                         (os.path.relpath(a, REPO) if a.startswith(REPO) else a)
                                         for a in args))
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        for line in p.stdout.decode("utf-8", "replace").splitlines()[-6:]:
            print("    | " + line)
        return p.returncode

    r0 = os.path.join(scratch, "rounds", "R-0000")
    good = os.path.join(REPO, "round", "mods", "demo-bw")
    bad = os.path.join(REPO, "round", "mods", "bad-net-key")
    expect("open", run("open", "--np", NP0, "--manifest", genesis, "--out", r0) == 0)
    expect("submit hello-bw", run("submit", r0, "--mod", HELLO, "--sha256", pin_of(HELLO),
                                  "--seat", "MOD-SEAT") == 0)
    expect("submit demo-bw", run("submit", r0, "--mod", good, "--sha256", pin_of(good),
                                 "--seat", "ROUND-SEAT") == 0)
    expect("submit bad-net-key", run("submit", r0, "--mod", bad, "--sha256", pin_of(bad),
                                     "--seat", "DEMO-BAD") == 0)
    rc = run("judge", r0,
             "--laws", os.path.join(REPO, "laws", "laws.py"),
             "--package", os.path.join(MOD_DIR, "package.py"),
             "--sorter", os.path.join(REPO, "sorter", "sorter.py"),
             "--base", os.path.join(REPO, "base", "base.py"))
    expect("judge exits 1 because the planted-bad mod FAILs", rc == 1)
    for name in sorted(os.listdir(r0)):
        if name.startswith("score-S-") and name.endswith(".json"):
            with open(os.path.join(r0, name), "rb") as f:
                s = json.loads(f.read().decode("utf-8"))
            laws = " ".join("%s=%s" % (k, v["result"]) for k, v in sorted(s["laws"].items()))
            print("  %s %-12s overall=%s  %s" % (name[:-5], s["mod_id"], s["overall"], laws))
    with open(os.path.join(r0, "evidence", "order.json"), "rb") as f:
        order = json.loads(f.read().decode("utf-8"))["order_round"]
    print("  sorter order: %s  (%s)" % (order.get("ids"), order.get("result")))
    expect("sorter puts hello-bw before demo-bw", order.get("ids") == ["hello-bw", "demo-bw"])
    expect("close", run("close", r0) == 0)
    with open(os.path.join(r0, "round.json"), "rb") as f:
        np1 = json.loads(f.read().decode("utf-8"))["closed_as"]
    print("  closed as new named point %s (supersedes %s)" % (np1, NP0))


def step_retro():
    print("\n== 4. memory-retro on synthetic fixtures")
    payload = os.path.join(REPO, "memory-retro", "payload")
    mr = load_module("memory_retro", os.path.join(payload, "memory_retro.py"))
    fx = load_module("fixtures", os.path.join(payload, "fixtures.py"))
    good = mr.run({"schema": mr.REQ, "events": fx.good(), "label": "good"})
    extra, want = fx.DEFECTS["unsourced_hash"]
    bad = mr.run({"schema": mr.REQ, "events": fx.good() + extra, "label": "planted"})
    g = good["memory_continuity"]["hash_provenance"]["counts"]
    b = bad["memory_continuity"]["hash_provenance"]["counts"]
    print("  clean   hash_provenance %s" % json.dumps(g, sort_keys=True))
    print("  planted hash_provenance %s" % json.dumps(b, sort_keys=True))
    expect("planted unsourced hash is counted", b.get("UNSOURCED") == want["provenance.UNSOURCED"])
    again = mr.run({"schema": mr.REQ, "events": list(reversed(fx.good())), "label": "good"})
    expect("result is order independent", again == good)


def main():
    scratch = tempfile.mkdtemp(prefix="agape-demo-")
    print("Agape demo. scratch: %s" % scratch)
    try:
        step_manager(step_package())
        step_round(scratch)
        step_retro()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    print("\nDEMO %s" % ("PASS" if not problems else "FAIL: " + "; ".join(problems)))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
