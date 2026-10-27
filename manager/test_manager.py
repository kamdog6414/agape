"""Muse Spark - MANAGER-SEAT

Manager v1 tests. Stdlib unittest. No network, deterministic.
Package tests use the Round 0 hello-bw delivery in the tree and skip
with a reason where the delivery is absent.
Run: python -B test_manager.py   (from this directory)
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from manager import (  # noqa: E402
    ACCEPTED_BASE,
    NAMED_POINT,
    VERSION,
    open_manager,
    read_package,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
HELLO_DIR = HERE.parent / "mod" / "ROUND0" / "packages" / "hello-bw"
HELLO_PIN = "f06effb9c5912625c5c07153663b35ad1fa9d0daf66458b8f40b370c7ee6e477"
HELLO_READER_SHA = "f480d6141d075e719a12cb9a0b76da37993daf1d40e00128f45cc1bf7689c8a0"
HAS_HELLO = (HELLO_DIR / "MANIFEST.json").is_file()


class ManagerTest(unittest.TestCase):
    def test_install_then_enable_then_disable(self) -> None:
        m = open_manager("BOX-A")
        self.assertEqual(m.install("alpha", SHA_A)["result"], "installed")
        row = m.enable("alpha")
        self.assertEqual(row["result"], "enabled")
        self.assertEqual(row["base_result"], "enabled")
        self.assertEqual(m.core.list_order(), ["alpha"])
        row = m.disable("alpha")
        self.assertEqual(row["result"], "disabled")
        self.assertEqual(m.core.list_order(), [])

    def test_install_rejects_bad_id_and_bad_sha(self) -> None:
        m = open_manager("BOX-A")
        self.assertEqual(m.install("", SHA_A)["result"], "refused")
        self.assertEqual(m.install("has space", SHA_A)["result"], "refused")
        self.assertEqual(m.install("alpha", "zzz")["result"], "refused")
        self.assertEqual(m.install("alpha", "A" * 64)["result"], "refused")
        self.assertEqual(m.install("alpha", SHA_A)["result"], "installed")
        self.assertEqual(m.install("alpha", SHA_B)["result"], "refused")

    def test_enable_unknown_is_refused_without_touching_base(self) -> None:
        m = open_manager("BOX-A")
        row = m.enable("ghost")
        self.assertEqual(row["result"], "refused")
        self.assertEqual(row["base_result"], "not_installed")
        self.assertEqual(m.core.list_order(), [])
        self.assertEqual(m.core.receipts(), [])

    def test_double_enable_refused_by_base(self) -> None:
        m = open_manager("BOX-A")
        m.install("alpha", SHA_A)
        self.assertEqual(m.enable("alpha")["result"], "enabled")
        self.assertEqual(m.enable("alpha")["result"], "refused")

    def test_disable_unknown_is_refused(self) -> None:
        m = open_manager("BOX-A")
        self.assertEqual(m.disable("ghost")["result"], "refused")

    @unittest.skipUnless(HAS_HELLO, "hello-bw delivery absent from this tree")
    def test_install_hello_bw_from_package(self) -> None:
        m = open_manager("BOX-A")
        row = m.install_from_package(HELLO_DIR, HELLO_PIN)
        self.assertEqual(row["result"], "installed")
        self.assertEqual(row["mod_id"], "hello-bw")
        self.assertEqual(row["manifest_sha256"], HELLO_PIN)
        self.assertEqual(row["reader_sha256"], HELLO_READER_SHA)
        self.assertEqual(m.enable("hello-bw")["result"], "enabled")
        self.assertEqual(m.core.list_order(), ["hello-bw"])
        self.assertEqual(m.disable("hello-bw")["result"], "disabled")
        self.assertEqual(m.core.list_order(), [])

    @unittest.skipUnless(HAS_HELLO, "hello-bw delivery absent from this tree")
    def test_package_pin_mismatch_is_refused(self) -> None:
        m = open_manager("BOX-A")
        row = m.install_from_package(HELLO_DIR, "0" * 64)
        self.assertEqual(row["result"], "refused")
        self.assertIn("PackageError", row["reason"])
        self.assertEqual(m.installed(), {})

    @unittest.skipUnless(HAS_HELLO, "hello-bw delivery absent from this tree")
    def test_tampered_package_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agape-mgr-") as tmp:
            copy = Path(tmp) / "hello-bw"
            shutil.copytree(HELLO_DIR, copy)
            target = copy / "payload" / "hello_bw.py"
            data = bytearray(target.read_bytes())
            data[0] ^= 1
            target.write_bytes(bytes(data))
            m = open_manager("BOX-A")
            row = m.install_from_package(copy, HELLO_PIN)
            self.assertEqual(row["result"], "refused")
            self.assertEqual(m.installed(), {})

    def test_change_log_is_append_only_and_ordered(self) -> None:
        m = open_manager("BOX-A")
        m.install("alpha", SHA_A)
        m.enable("alpha")
        m.disable("alpha")
        m.disable("ghost")
        got = [(c["action"], c["mod_id"], c["result"]) for c in m.changes()]
        self.assertEqual(
            got,
            [
                ("install", "alpha", "installed"),
                ("enable", "alpha", "enabled"),
                ("disable", "alpha", "disabled"),
                ("disable", "ghost", "refused"),
            ],
        )
        for c in m.changes():
            self.assertRegex(c["ts_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_versions_and_point(self) -> None:
        self.assertEqual(VERSION, "agape.manager.v1")
        self.assertEqual(ACCEPTED_BASE, ("agape.base.v0", "agape.base.v1"))
        self.assertEqual(NAMED_POINT, "NP-20261026T170000Z")
        m = open_manager("BOX-A")
        self.assertIn(m.base_version, ACCEPTED_BASE)
        self.assertEqual(m.core.probe()["named_point"], "NP-20261026T170000Z")


if __name__ == "__main__":
    unittest.main(verbosity=1)
