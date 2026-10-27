#!/usr/bin/env python3
"""round.py v0.3 test: Round 0 (LAWS v1) end to end offline, then Rounds 1
and 2 under LAWS v2 (chain depth 1 and 2), plus chain tamper cases.

Python 3 stdlib only. Run: python3 -B test_round.py [--scratch DIR]
Everything comes from this repository: laws/laws.py, laws/laws_v2.py,
base/base.py, mod/ROUND0/package.py, mod/ROUND0/packages/hello-bw,
sorter/sorter.py and conformance/conformance.py. A zip of the MOD folder is
built in scratch so archive submission is exercised too.

The real genesis manifest is not shipped (it lists private machine paths).
This test writes a synthetic genesis manifest named NP-20261026T170000Z in
scratch and points AGAPE_GENESIS_SHA256 at it for the round.py child
processes only. Exit 0 = every check PASS.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ROUND = os.path.join(HERE, "round.py")
CONFORMANCE = os.path.join(REPO, "conformance", "conformance.py")
MOD_DIR = os.path.join(REPO, "mod", "ROUND0")
HELLO_DIR = os.path.join(MOD_DIR, "packages", "hello-bw")
NP0 = "NP-20261026T170000Z"
ENV = dict(os.environ)

results = []


def check(label, ok, detail=""):
    results.append(bool(ok))
    print("%s %s%s" % ("PASS" if ok else "FAIL", label,
                       ("  (" + detail + ")") if detail else ""))


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load(path):
    with open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def pin_of(moddir):
    with open(moddir.rstrip("/") + ".MANIFEST.sha256") as f:
        return f.read().split()[0]


HELLO_PIN = pin_of(HELLO_DIR)


def run(*args):
    cmd = [sys.executable, "-B", ROUND, "--conformance", CONFORMANCE] + list(args)
    print("$ round.py " + " ".join(args))
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=ENV)
    out = p.stdout.decode("utf-8", "replace")
    for line in out.rstrip("\n").splitlines():
        print("  | " + line)
    print("  exit %d" % p.returncode)
    return p.returncode, out


def sidecar_ok(path):
    with open(path + ".sha256") as f:
        return f.read().split()[0] == sha(path)


def write_genesis(folder):
    """A synthetic stand-in for the genesis named-point manifest."""
    os.makedirs(folder)
    path = os.path.join(folder, "MANIFEST.json")
    data = {"format": "fullcircle.named-point.v1", "name": NP0,
            "note": "synthetic demo genesis; not the real point manifest",
            "files": []}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def zip_mod(dest):
    """Zip package.py and packages/hello-bw the way a MOD bundle ships."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(MOD_DIR, "package.py"), "package.py")
        for root, _dirs, files in os.walk(HELLO_DIR):
            for name in sorted(files):
                full = os.path.join(root, name)
                z.write(full, os.path.relpath(full, MOD_DIR).replace(os.sep, "/"))
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", default=None,
                    help="scratch dir (default: a new temp dir, removed on PASS)")
    given = ap.parse_args().scratch
    scratch = given or tempfile.mkdtemp(prefix="agape-round-test-")
    if given and os.path.isdir(scratch):
        shutil.rmtree(scratch)
    os.makedirs(scratch, exist_ok=True)
    print("agape round v0.3 test. scratch: %s" % scratch)

    np0_manifest = write_genesis(os.path.join(scratch, "genesis", NP0))
    NP0_SHA = sha(np0_manifest)
    ENV["AGAPE_GENESIS_SHA256"] = NP0_SHA
    ENV["PYTHONDONTWRITEBYTECODE"] = "1"
    laws_py = os.path.join(REPO, "laws", "laws.py")
    laws_v2_py = os.path.join(REPO, "laws", "laws_v2.py")
    base_py = os.path.join(REPO, "base", "base.py")
    package_py = os.path.join(MOD_DIR, "package.py")
    sorter_py = os.path.join(REPO, "sorter", "sorter.py")
    tracked = (laws_py, laws_v2_py, base_py, package_py, sorter_py,
               os.path.join(HELLO_DIR, "MANIFEST.json"))
    before = {p: sha(p) for p in tracked}
    mod_zip = zip_mod(os.path.join(scratch, "MOD-ROUND0.zip"))
    MOD_ZIP_SHA = sha(mod_zip)
    check("repository modules present", all(os.path.isfile(p) for p in tracked))
    check("hello-bw pin matches its MANIFEST.json bytes",
          sha(os.path.join(HELLO_DIR, "MANIFEST.json")) == HELLO_PIN)

    demo = os.path.join(HERE, "mods", "demo-bw")
    bad = os.path.join(HERE, "mods", "bad-net-key")
    # a tampered COPY of hello-bw: one payload byte flipped, real pin kept
    tamper = os.path.join(scratch, "tamper", "hello-bw")
    shutil.copytree(HELLO_DIR, tamper)
    tp = os.path.join(tamper, "payload", "hello_bw.py")
    with open(tp, "rb") as f:
        data = bytearray(f.read())
    data[-2] = data[-2] ^ 1
    with open(tp, "wb") as f:
        f.write(bytes(data))

    r0 = os.path.join(scratch, "rounds", "R-0000")
    r1 = os.path.join(scratch, "rounds", "R-0001")

    print("\n== Round 0: open")
    rc, _ = run("open", "--np", NP0, "--manifest", np0_manifest, "--out", r0)
    rj = load(os.path.join(r0, "round.json"))
    check("open exit 0", rc == 0)
    check("round id R-0000", rj["round_id"] == "R-0000")
    check("round.json records named point and its sha256",
          rj["named_point"] == NP0 and rj["manifest"]["sha256"] == NP0_SHA)
    check("round.json has sidecar", sidecar_ok(os.path.join(r0, "round.json")))
    chain = os.path.join(scratch, "rounds", "chain")
    check("Round 0 is LAWS v1; genesis seeded in the chain dir",
          rj["laws_version"] == "v1" and rj["chain_dir"] == chain
          and sha(os.path.join(chain, NP0, "MANIFEST.json")) == NP0_SHA)

    print("\n== Round 0: submit")
    rcs = [
        run("submit", r0, "--mod", demo, "--sha256", pin_of(demo), "--seat", "ROUND-SEAT")[0],
        run("submit", r0, "--mod", mod_zip, "--member", "packages/hello-bw",
            "--sha256", HELLO_PIN, "--seat", "MOD-SEAT")[0],
        run("submit", r0, "--mod", bad, "--sha256", pin_of(bad), "--seat", "DEMO-BAD")[0],
        run("submit", r0, "--mod", tamper, "--sha256", HELLO_PIN, "--seat", "DEMO-TAMPER")[0],
    ]
    rj = load(os.path.join(r0, "round.json"))
    check("four submissions recorded", rcs == [0, 0, 0, 0] and
          [s["submission_id"] for s in rj["submissions"]] ==
          ["S-001", "S-002", "S-003", "S-004"])
    s2 = load(os.path.join(r0, "submissions", "S-002", "submission.json"))
    check("hello-bw identity is the raw MANIFEST.json sha256",
          s2["manifest_sha256_observed"] == HELLO_PIN and s2["schema"] == "agape.mod.v0")
    check("bundle provenance recorded",
          s2["archive"]["sha256"] == MOD_ZIP_SHA
          and s2["archive"]["member"] == "packages/hello-bw")

    print("\n== Round 0: judge (under unshare -rn)")
    rc, out = run("judge", r0, "--laws", laws_py, "--package", package_py,
                  "--sorter", sorter_py, "--base", base_py, "--netns")
    check("judge exit 1 (FAILs present)", rc == 1)
    sc = {i: load(os.path.join(r0, "score-S-00%d.json" % i)) for i in (1, 2, 3, 4)}
    off = sc[1]["run_offline"]
    if "worked" in off["unshare"]:
        check("offline evidence: child netns, only lo, no routes",
              off["verdict"] == "OFFLINE_NAMESPACE" and off["interfaces"] == ["lo"]
              and off["route_rows"] == 0 and off["run_netns"] != off["host_netns"])
    else:
        check("offline evidence records that unshare is unavailable",
              off["verdict"] == "NOT_PROVEN_OFFLINE", off["unshare"])
    offtxt = open(os.path.join(r0, off["evidence_path"])).read()
    check("offline evidence from /proc/net/dev and /proc/net/route",
          "--- /proc/net/dev" in offtxt and "--- /proc/net/route" in offtxt
          and sidecar_ok(os.path.join(r0, off["evidence_path"])))
    for i in (1, 2):
        s = sc[i]
        check("%s: verify_package, four laws, CONFORMS, enable, sorter all PASS" % s["mod_id"],
              s["package_verify"]["result"] == "PASS"
              and all(v["result"] == "PASS" for v in s["laws"].values())
              and len(s["laws"]) == 4
              and s["conformance"]["verdict"] == "CONFORMS"
              and s["base_enable"]["result"] == "PASS"
              and s["sorter"]["result"] == "PASS" and s["overall"] == "PASS")
    check("Sorter order: hello-bw before demo-bw (demo-bw requires hello-bw)",
          sc[1]["sorter"]["ids"] == ["hello-bw", "demo-bw"]
          and sc[2]["sorter"]["position"] == 1 and sc[1]["sorter"]["position"] == 2)
    order = load(os.path.join(r0, "evidence", "order.json"))
    check("order_round applied through core.set_order",
          order["order_round"]["applied"] is True
          and order["order_round"]["receipt"]["action"] == "set_order"
          and order["probe"]["order"] == ["hello-bw", "demo-bw"])
    b = sc[3]
    check("Round 0 scores are LAWS v1, conformance wrapper records the round NP",
          all(s["laws_version"] == "v1" for s in sc.values())
          and sc[2]["conformance"]["named_point"] == NP0
          and sidecar_ok(os.path.join(r0, sc[2]["conformance"]["np_wrapper_path"])))
    check("bad mod: verify_package PASS (format is fine)",
          b["package_verify"]["result"] == "PASS")
    check("bad mod: no_network FAIL", b["laws"]["no_network"]["result"] == "FAIL")
    check("bad mod: no_secrets_in_mod FAIL", b["laws"]["no_secrets_in_mod"]["result"] == "FAIL")
    check("bad mod: not enabled, not ordered, overall FAIL",
          b["base_enable"]["result"] == "NOT_RUN" and b["sorter"]["position"] is None
          and b["overall"] == "FAIL")
    t = sc[4]
    vtxt = open(os.path.join(r0, t["package_verify"]["evidence_path"])).read()
    check("tampered copy: verify_package FAIL, payload SHA256 mismatch",
          t["package_verify"]["result"] == "FAIL" and "payload: SHA256 mismatch" in vtxt)
    check("tampered copy: payload laws NOT_RUN, overall FAIL",
          t["laws"]["no_network"]["result"] == "NOT_RUN" and t["overall"] == "FAIL")
    check("tampered copy: not enabled, no sorter position (same mod_id as S-002)",
          t["base_enable"]["result"] == "NOT_RUN" and t["sorter"]["position"] is None)
    ev_ok = True
    for s in sc.values():
        for v in list(s["laws"].values()) + [s["package_verify"]]:
            p = os.path.join(r0, v["evidence_path"])
            ev_ok = ev_ok and sha(p) == v["evidence_sha256"] and sidecar_ok(p)
    check("every evidence file matches its recorded sha256 and sidecar", ev_ok)
    check("every score receipt has a matching .sha256 sidecar",
          all(sidecar_ok(os.path.join(r0, "score-S-00%d.json" % i)) for i in sc))

    print("\n== Round 0: close")
    rc, _ = run("close", r0)
    rj = load(os.path.join(r0, "round.json"))
    np1 = rj["closed_as"]
    man_path = os.path.join(r0, "close", np1 + ".json")
    man = load(man_path)
    man_sha = sha(man_path)
    check("close exit 0", rc == 0)
    check("new named point id NP-<UTC stamp>",
          np1.startswith("NP-") and np1.endswith("Z") and len(np1) == 19, np1)
    check("close manifest sidecar matches", sidecar_ok(man_path))
    check("hash chain: close manifest names previous NP and its sha256",
          man["prev_np_id"] == NP0 and man["prev_manifest_sha256"] == NP0_SHA)
    check("close writes LAWS v2 link: name and supersedes.sha256",
          man["name"] == np1 and man["supersedes"]["sha256"] == NP0_SHA
          and man["supersedes"]["np_id"] == NP0)
    np1_chain = os.path.join(chain, np1, "MANIFEST.json")
    check("close point copied byte-exact into chain/<NP>/MANIFEST.json",
          os.path.isfile(np1_chain) and sha(np1_chain) == man_sha)
    listed = {e["path"]: e["sha256"] for e in man["files"]}
    needs_path = os.path.join(r0, "close", "needs.json")
    needs = load(needs_path)["needs"]
    check("close manifest pins round.json and needs.json",
          listed.get("round.json") == sha(os.path.join(r0, "round.json"))
          and man["needs_sha256"] == sha(needs_path)
          and listed.get("close/needs.json") == sha(needs_path))
    bad_needs = [n for n in needs if "S-003" in n["title"]]
    check("bad mod's FAILs became NEEDs",
          {n["law"] for n in bad_needs} == {"no_network", "no_secrets_in_mod"},
          ", ".join(n["id"] for n in bad_needs))
    t_needs = [n for n in needs if "S-004" in n["title"]]
    check("tampered package became one package_verify NEED",
          [n["law"] for n in t_needs] == ["package_verify"])
    check("good mods made no NEED",
          not [n for n in needs if "S-001" in n["title"] or "S-002" in n["title"]])
    check("NEEDs are N-xxx with a 'what this shows we need' line",
          all(n["id"].startswith("N-") and n["what_this_shows_we_need"] for n in needs))

    print("\n== Round 0: verify closed round")
    rc, _ = run("verify", r0, "--scratch", os.path.join(scratch, "verify"))
    check("verify exit 0 (round dir CONFORMS to its close manifest)", rc == 0)

    print("\n== Round 1: refuse a tampered needs file")
    bent = os.path.join(scratch, "needs-tampered.json")
    with open(needs_path, "rb") as f:
        data = f.read()
    with open(bent, "wb") as f:
        f.write(data.replace(b"open", b"done", 1))
    rc, _ = run("open", "--np", np1, "--manifest", man_path, "--needs", bent,
                "--out", os.path.join(scratch, "rounds", "R-bent"))
    check("open refuses needs not pinned by the close manifest", rc == 2)

    print("\n== Round 1: open from Round 0 close (LAWS v2)")
    rc, _ = run("open", "--np", np1, "--manifest", np1_chain, "--needs",
                needs_path, "--out", r1)
    r1j = load(os.path.join(r1, "round.json"))
    check("open Round 1 exit 0, round id R-0001", rc == 0 and r1j["round_id"] == "R-0001")
    check("hash chain: Round 1 opens on Round 0 close manifest sha256",
          r1j["named_point"] == np1 and r1j["manifest"]["sha256"] == man_sha)
    check("Round 1 carries every Round 0 NEED",
          [n["id"] for n in needs] == [n["id"] for n in r1j["needs"]])
    check("Round 1 is LAWS v2 on its own point, same chain dir",
          r1j["laws_version"] == "v2" and r1j["laws_manifest"] == np1_chain
          and r1j["chain_dir"] == chain)

    judge_args = ["--laws", laws_py, "--laws-v2", laws_v2_py, "--package", package_py,
                  "--sorter", sorter_py, "--base", base_py, "--netns"]

    def judge_hello(rdir, label):
        run("submit", rdir, "--mod", mod_zip, "--member", "packages/hello-bw",
            "--sha256", HELLO_PIN, "--seat", "MOD-SEAT")
        rc, _ = run("judge", rdir, *judge_args)
        return rc, load(os.path.join(rdir, "score-S-001.json"))

    rc, s1 = judge_hello(r1, "R1")
    pv1 = s1["laws"]["named_point_hash"]["point_verification"]
    check("Round 1 hello-bw: L-11 PASS under LAWS v2 at chain depth 1",
          rc == 0 and s1["laws_version"] == "v2"
          and s1["laws"]["named_point_hash"]["result"] == "PASS"
          and pv1["depth"] == 1 and pv1["chain"] == [man_sha, NP0_SHA]
          and pv1["reason"] == "chained to genesis", "depth %d" % pv1["depth"])
    check("Round 1 hello-bw: all gates PASS, overall PASS",
          s1["overall"] == "PASS" and s1["package_verify"]["result"] == "PASS"
          and all(v["result"] == "PASS" for v in s1["laws"].values()))
    check("Round 1 conformance wrapper: NP is the round point, receipt stamped genesis",
          s1["conformance"]["named_point"] == np1
          and s1["conformance"]["receipt_stamped_named_point"] == NP0
          and load(os.path.join(r1, s1["conformance"]["np_wrapper_path"]))
          ["np_matches_receipt"] is False)

    print("\n== Round 1: close")
    rc, _ = run("close", r1)
    np2 = load(os.path.join(r1, "round.json"))["closed_as"]
    man2_path = os.path.join(r1, "close", np2 + ".json")
    man2 = load(man2_path)
    np2_chain = os.path.join(chain, np2, "MANIFEST.json")
    check("Round 1 close links to Round 0 point; new NP id distinct",
          rc == 0 and np2 != np1 and man2["supersedes"]["sha256"] == man_sha
          and sha(np2_chain) == sha(man2_path))
    rc, _ = run("chain", np2_chain, "--laws-v2", laws_v2_py)
    check("round.py chain walks the Round 1 point to genesis", rc == 0)

    print("\n== Round 2: open and judge (LAWS v2, depth 2)")
    r2 = os.path.join(scratch, "rounds", "R-0002")
    rc, _ = run("open", "--np", np2, "--manifest", np2_chain, "--needs",
                os.path.join(r1, "close", "needs.json"), "--out", r2)
    check("open Round 2 exit 0, round id R-0002",
          rc == 0 and load(os.path.join(r2, "round.json"))["round_id"] == "R-0002")
    rc, s2 = judge_hello(r2, "R2")
    pv2 = s2["laws"]["named_point_hash"]["point_verification"]
    check("Round 2 hello-bw: L-11 PASS under LAWS v2 at chain depth 2",
          rc == 0 and s2["laws"]["named_point_hash"]["result"] == "PASS"
          and pv2["depth"] == 2 and pv2["chain"] == [sha(man2_path), man_sha, NP0_SHA],
          "depth %d" % pv2["depth"])
    check("Round 2 hello-bw overall PASS", s2["overall"] == "PASS")

    print("\n== Tamper A: a parent manifest changed in the chain")
    ta = os.path.join(scratch, "tamper-a")
    shutil.copytree(chain, os.path.join(ta, "chain"))
    parent = os.path.join(ta, "chain", np1, "MANIFEST.json")
    with open(parent, "rb") as f:
        data = f.read()
    with open(parent, "wb") as f:
        f.write(data.replace(b"agape-round v0.3", b"agape-round v0.X", 1))
    check("tamper A changed the parent bytes", sha(parent) != man_sha)
    ra = os.path.join(ta, "R-0002")
    rc, _ = run("open", "--np", np2, "--manifest", os.path.join(ta, "chain", np2,
                "MANIFEST.json"), "--out", ra)
    rc, sa = judge_hello(ra, "TA")
    la = sa["laws"]["named_point_hash"]
    check("tamper A: L-11 FAIL with a reason",
          rc == 1 and la["result"] == "FAIL"
          and la["point_verification"]["reason"] == "parent manifest not found"
          and sa["overall"] == "FAIL", la.get("reason"))
    ev = open(os.path.join(ra, la["evidence_path"])).read()
    check("tamper A evidence names the reason and the broken link",
          "reason: parent manifest not found" in ev
          and la["point_verification"]["broken_link"]["supersedes_sha256"] == man_sha
          and la["point_verification"]["broken_link"]["supersedes_np_id"] == np1
          and "broken link: chain[0] supersedes %s %s" % (np1, man_sha) in ev)

    print("\n== Tamper B: the round's own point changed after open")
    tb = os.path.join(scratch, "tamper-b")
    shutil.copytree(chain, os.path.join(tb, "chain"))
    rb = os.path.join(tb, "R-0002")
    own = os.path.join(tb, "chain", np2, "MANIFEST.json")
    run("open", "--np", np2, "--manifest", own, "--out", rb)
    with open(own, "rb") as f:
        data = f.read()
    with open(own, "wb") as f:
        f.write(data.replace(b"agape-round v0.3", b"agape-round v0.X", 1))
    rc, sb = judge_hello(rb, "TB")
    lb = sb["laws"]["named_point_hash"]
    check("tamper B: laws_v2 still walks (links intact) but L-11 FAIL on the open pin",
          rc == 1 and lb["result"] == "FAIL"
          and lb["point_verification"]["verdict"] is True
          and lb["point_verification"]["open_pin_matches"] is False
          and lb["reason"].startswith("round manifest changed since open"), lb.get("reason"))

    check("repository files unchanged by the run",
          all(sha(p) == h for p, h in before.items()))

    n_pass, n_all = sum(results), len(results)
    print("\nRound 0 close NP: %s  sha256 %s" % (np1, man_sha))
    print("Round 1 close NP: %s  sha256 %s" % (np2, sha(man2_path)))
    print("Round 1 L-11: %s depth %d (%s)" % (s1["laws"]["named_point_hash"]["result"],
                                             pv1["depth"], pv1["reason"]))
    print("Round 2 L-11: %s depth %d (%s)" % (s2["laws"]["named_point_hash"]["result"],
                                             pv2["depth"], pv2["reason"]))
    print("Tamper A L-11: %s (%s)" % (la["result"], la["reason"]))
    print("Tamper B L-11: %s (%s)" % (lb["result"], lb["reason"]))
    for n in needs:
        print("%s %s" % (n["id"], n["title"]))
        print("  what this shows we need: %s" % n["what_this_shows_we_need"])
    print("\nRESULT: %d/%d PASS, %d FAIL" % (n_pass, n_all, n_all - n_pass))
    if n_pass == n_all and not given:
        shutil.rmtree(scratch)
    return 0 if n_pass == n_all else 1


if __name__ == "__main__":
    sys.exit(main())
