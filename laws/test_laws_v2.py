"""Muse Wonder - LAWS-SEAT

Tests for laws_v2.py and scorer_v2.py - Laws v2, Round 1.

Chain mechanics are tested on a synthetic point tree with the
genesis pin overridden to the synthetic root (the walk does not
know the difference; the real pin is asserted separately and
the real genesis manifest is verified when a copy is present).

Run: python3 test_laws_v2.py     (exit 0 = all pass)
"""

import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import laws_v2
import scorer_v2

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name
          + ((" -- " + str(detail)) if detail and not cond else ""))


def write_manifest(folder, name, parent_sha=None, alias=False):
    os.makedirs(folder, exist_ok=True)
    data = {"format": "fullcircle.named-point.v1", "name": name}
    if parent_sha is not None:
        if alias:
            data["parent_manifest_sha256"] = parent_sha
        else:
            data["supersedes"] = {"sha256": parent_sha}
    path = os.path.join(folder, "MANIFEST.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def file_sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        digest.update(fh.read())
    return digest.hexdigest()


# A copy of the real genesis manifest is not shipped (it lists private
# machine paths). Point AGAPE_GENESIS_MANIFEST at a copy to verify it.
REAL_GENESIS_CANDIDATES = [
    p for p in [os.environ.get("AGAPE_GENESIS_MANIFEST", "")] if p
]


def main():
    check("genesis pin is this morning's point",
          laws_v2.GENESIS_MANIFEST_SHA256
          == "e605b853d6eea415073da043a65d9f28fb8b715e669d4ece94b0c74"
             "bee88e7b7")

    real = next((p for p in REAL_GENESIS_CANDIDATES
                 if os.path.isfile(p)), None)
    if real:
        vp = laws_v2.verify_point(real)
        check("real genesis verifies at depth 0",
              vp["verdict"] and vp["depth"] == 0
              and vp["point"] == "NP-20261026T170000Z", vp)
    else:
        print("SKIP real genesis (no copy on this box)")

    root = tempfile.mkdtemp(prefix="laws-v2-")
    points = os.path.join(root, "points")
    g_path = write_manifest(os.path.join(points, "NP-G"), "NP-G")
    g_sha = file_sha(g_path)
    saved_pin = laws_v2.GENESIS_MANIFEST_SHA256
    laws_v2.GENESIS_MANIFEST_SHA256 = g_sha
    try:
        vp = laws_v2.verify_point(g_path)
        check("synthetic genesis verifies", vp["verdict"]
              and vp["depth"] == 0, vp)

        c_path = write_manifest(os.path.join(points, "NP-C"),
                                "NP-C", parent_sha=g_sha)
        vp = laws_v2.verify_point(c_path)
        check("child point chains to genesis", vp["verdict"]
              and vp["depth"] == 1 and vp["chain"][0] == file_sha(c_path)
              and vp["chain"][-1] == g_sha, vp)

        gc_path = write_manifest(os.path.join(points, "NP-GC"),
                                 "NP-GC", parent_sha=file_sha(c_path),
                                 alias=True)
        vp = laws_v2.verify_point(gc_path)
        check("grandchild chains (alias field)", vp["verdict"]
              and vp["depth"] == 2, vp)

        bad_path = write_manifest(os.path.join(points, "NP-BAD"),
                                  "NP-BAD", parent_sha="0" * 64)
        vp = laws_v2.verify_point(bad_path)
        check("unknown parent fails", not vp["verdict"]
              and vp["reason"] == "parent manifest not found", vp)

        orphan = write_manifest(os.path.join(points, "NP-ORPHAN"),
                                "NP-ORPHAN")
        vp = laws_v2.verify_point(orphan)
        check("no parent link fails", not vp["verdict"]
              and vp["reason"] == "no parent link", vp)

        a_path = write_manifest(os.path.join(points, "NP-A"), "NP-A",
                                parent_sha="f" * 64)
        b_path = write_manifest(os.path.join(points, "NP-B"), "NP-B",
                                parent_sha=file_sha(a_path))
        # Close the cycle: rewrite A pointing at B.
        a_path = write_manifest(os.path.join(points, "NP-A"), "NP-A",
                                parent_sha=file_sha(b_path))
        vp = laws_v2.verify_point(a_path)
        check("cycle fails, does not hang", not vp["verdict"], vp)

        fix = os.path.join(root, "cleanmod")
        os.makedirs(fix)
        with open(os.path.join(fix, "main.py"), "w") as fh:
            fh.write("print('plain')\n")
        res = laws_v2.evaluate(fix, c_path)
        check("evaluate: clean mod, chained point, all pass",
              all(res.values()), res)
        names = laws_v2.passed_names(fix, c_path)
        check("passed_names returns all four",
              names == list(laws_v2.PREDICATES), names)

        outdir = os.path.join(root, "scores")
        path, receipt = scorer_v2.score_mod(fix, c_path, outdir)
        check("scorer_v2 receipt overall PASS with chain",
              receipt["overall"] == "PASS"
              and receipt["point_verification"]["depth"] == 1
              and receipt["point"] == "NP-C", receipt)
    finally:
        laws_v2.GENESIS_MANIFEST_SHA256 = saved_pin

    failed = [n for n, ok in RESULTS if not ok]
    print("-" * 60)
    print(str(len(RESULTS) - len(failed)) + "/" + str(len(RESULTS))
          + " passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
