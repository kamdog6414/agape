#!/usr/bin/env python3
"""Run every test in this repository, then the demo, each under python -B
in its own process with PYTHONDONTWRITEBYTECODE=1 (no caches written).

    python3 -B run_tests.py

Exit 0 only if every suite passes.
"""

import os
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
SUITES = [
    ("base", "base", ["test_base.py"]),
    ("manager", "manager", ["-m", "unittest", "-v", "test_manager"]),
    ("sorter", "sorter", ["-m", "unittest", "-v", "test_sorter"]),
    ("laws v1", "laws", ["test_laws.py"]),
    ("laws v2", "laws", ["test_laws_v2.py"]),
    ("conformance", "conformance", ["-m", "unittest", "-v", "test_conformance"]),
    ("memory-retro", os.path.join("memory-retro", "payload"),
     ["-m", "unittest", "-v", "test_memory_retro"]),
    ("round", "round", ["test_round.py"]),
    ("demo", ".", ["demo.py"]),
]


def main():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    failed = []
    for name, folder, args in SUITES:
        print("=" * 60)
        print("%s: python -B %s  (in %s)" % (name, " ".join(args), folder))
        p = subprocess.run([sys.executable, "-B"] + args, cwd=os.path.join(REPO, folder),
                           env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = p.stdout.decode("utf-8", "replace").rstrip().splitlines()
        for line in out[-4:]:
            print("  | " + line)
        print("  %s (exit %d)" % ("PASS" if p.returncode == 0 else "FAIL", p.returncode))
        if p.returncode != 0:
            failed.append(name)
    print("=" * 60)
    print("ALL PASS" if not failed else "FAILED: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
