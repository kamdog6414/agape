"""Muse Wonder - LAWS-SEAT

Tests for Agape Laws v1 predicates, composed against the real Base
on this box. Run: python3 test_laws.py [manifest_path]
With no manifest path, a synthetic genesis manifest is written to a temp
directory and the laws pin is pointed at it for this process only.
Exit 0 = all tests pass.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "base"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import laws
from base import open_base


def write(root: str, name: str, text: str) -> None:
    with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
        fh.write(text)


def main() -> int:
    failures = []
    synthetic = None
    if len(sys.argv) > 1:
        manifest_path = sys.argv[1]
    else:
        synthetic = tempfile.TemporaryDirectory()
        manifest_path = os.path.join(synthetic.name, "MANIFEST.json")
        with open(manifest_path, "w", encoding="utf-8") as fh:
            fh.write('{"format": "fullcircle.named-point.v1", '
                     '"name": "NP-20261026T170000Z", "note": "synthetic"}\n')
        import hashlib
        with open(manifest_path, "rb") as fh:
            laws.NAMED_POINT_MANIFEST_SHA256 = hashlib.sha256(fh.read()).hexdigest()

    def check(label: str, got, want) -> None:
        ok = got == want
        print(("PASS " if ok else "FAIL ") + label)
        if not ok:
            failures.append(label + ": got " + repr(got)
                            + " want " + repr(want))

    with tempfile.TemporaryDirectory() as tmp:
        clean = os.path.join(tmp, "clean-mod")
        dirty = os.path.join(tmp, "dirty-mod")
        os.makedirs(clean)
        os.makedirs(dirty)
        write(clean, "mod.json", '{"id": "clean", "kind": "note"}\n')
        write(clean, "note.md", "A plain black and white note.\n")
        write(dirty, "mod.json", '{"id": "dirty", "kind": "note"}\n')
        write(dirty, "run.py",
              "import socket\napi_key = \"abcd1234efgh5678\"\n")
        write(dirty, "ui.txt", "banner: \x1b[31mred\x1b[0m\n")

        check("clean mod passes all four",
              laws.passed_names(clean, manifest_path),
              list(laws.PREDICATES))
        check("dirty mod passes only named_point_hash",
              laws.passed_names(dirty, manifest_path),
              ["named_point_hash"])
        check("missing manifest fails named_point_hash",
              laws.named_point_hash(os.path.join(tmp, "absent.json")),
              False)
        check("dirty secret hits are reported by path",
              len(laws.secret_hits(dirty)), 1)
        check("dirty network hits are reported by path",
              len(laws.network_hits(dirty)), 1)
        check("dirty color hits are reported by path",
              len(laws.color_hits(dirty)), 1)

        core = open_base("BOX-C")
        names = laws.passed_names(clean, manifest_path)
        receipt = core.note_laws(names)
        check("note_laws accepts the passed names",
              receipt["result"], "enabled")
        probe = core.probe()
        check("probe records the law names",
              probe["laws"], list(laws.PREDICATES))
        check("probe names the point",
              probe["named_point"], laws.NAMED_POINT)
        print("PROBE " + json.dumps(probe, sort_keys=True))

    if synthetic is not None:
        synthetic.cleanup()
    if failures:
        print("FAILURES " + repr(failures))
        return 1
    print("ALL TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
