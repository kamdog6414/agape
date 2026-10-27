#!/usr/bin/env python3
"""Tests for conformance.py. Standard library only: python3 test_conformance.py -v"""

import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import conformance as C  # noqa: E402

# Optional: a copy of the real genesis manifest (not shipped).
NP_MANIFEST = os.environ.get("AGAPE_GENESIS_MANIFEST", "")


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = C.main(argv)
    return rc, buf.getvalue()


def load(path):
    with open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def check_sidecar(tc, path):
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(path + ".sha256") as f:
        line = f.read()
    tc.assertEqual(line, "%s  %s\n" % (digest, os.path.basename(path)))


class ConformanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="agape-conf-")
        self.base = os.path.join(self.tmp, "base")
        write(os.path.join(self.base, "README.md"), b"# Base\n")
        write(os.path.join(self.base, "mods", "alpha.py"), b"print('a')\n")
        write(os.path.join(self.base, "mods", "beta.py"), b"print('b')\n")
        write(os.path.join(self.base, "laws", "law1.txt"), b"law one\n")
        write(os.path.join(self.base, "sorter", "order.json"), b"[1,2,3]\n")
        # sensitive files in Base: must be listed by name, never hashed
        write(os.path.join(self.base, "api_token.txt"), b"SECRET-T\n")
        write(os.path.join(self.base, "conf", "prod.env"), b"SECRET-E\n")
        self.base_json = os.path.join(self.tmp, "base.json")
        rc, out = run(["manifest", self.base, "--out", self.base_json])
        self.assertEqual(rc, 0, out)

    def tearDown(self):
        for dp, dn, fn in os.walk(self.tmp):
            for n in dn + fn:
                try:
                    os.chmod(os.path.join(dp, n), 0o700)
                except OSError:
                    pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def copy_base(self, name):
        dst = os.path.join(self.tmp, name)
        shutil.copytree(self.base, dst)
        return dst

    def test_manifest_shape(self):
        m = load(self.base_json)
        paths = [e["path"] for e in m["files"]]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(paths, ["README.md", "laws/law1.txt", "mods/alpha.py",
                                 "mods/beta.py", "sorter/order.json"])
        self.assertEqual(m["file_count"], 5)
        self.assertEqual(m["entries_sha256"], C.entries_hash(m["files"]))
        e = m["files"][0]
        self.assertEqual(e["bytes"], len(b"# Base\n"))
        self.assertEqual(e["sha256"], hashlib.sha256(b"# Base\n").hexdigest())
        excl = {x["path"]: x["reason"] for x in m["excluded"]}
        self.assertEqual(excl.get("api_token.txt"), "sensitive name, not opened")
        self.assertEqual(excl.get("conf/prod.env"), "sensitive name, not opened")
        with open(self.base_json, "rb") as f:
            raw = f.read()
        self.assertNotIn(b"SECRET", raw)
        self.assertNotIn(hashlib.sha256(b"SECRET-T\n").hexdigest().encode(), raw)
        check_sidecar(self, self.base_json)

    def test_a_identical_copy_conforms(self):
        box = self.copy_base("box_a")
        rj = os.path.join(self.tmp, "receipt_a.json")
        rc, out = run(["check", self.base_json, box, "--box", "BOX-B",
                       "--out", rj])
        print("\n[test a] " + out.strip().replace("\n", "\n[test a] "))
        self.assertEqual(rc, 0)
        r = load(rj)
        self.assertEqual(r["verdict"], "CONFORMS")
        self.assertEqual(r["header"], "Grok Bot - ROUND-SEAT")
        self.assertEqual(r["box"], "BOX-B")
        self.assertEqual(r["named_point"], "NP-20261026T170000Z")
        self.assertTrue(r["checked_at_utc"].endswith("Z"))
        with open(self.base_json, "rb") as f:
            base_raw = f.read()
        self.assertEqual(r["base_manifest"]["sha256"],
                         hashlib.sha256(base_raw).hexdigest())
        self.assertEqual(r["counts"]["MATCH"], 5)
        for k in ("CHANGED", "MISSING", "EXTRA", "UNVERIFIED"):
            self.assertEqual(r["counts"][k], 0, k)
            self.assertEqual(r[k], [], k)
        check_sidecar(self, rj)

    def test_b_changed_missing_extra(self):
        box = self.copy_base("box_b")
        write(os.path.join(box, "mods", "alpha.py"), b"print('A changed')\n")
        os.remove(os.path.join(box, "laws", "law1.txt"))
        write(os.path.join(box, "mods", "gamma.py"), b"print('extra')\n")
        rj = os.path.join(self.tmp, "receipt_b.json")
        rc, out = run(["check", self.base_json, box, "--box", "BOX-A",
                       "--out", rj])
        print("\n[test b] " + out.strip().replace("\n", "\n[test b] "))
        self.assertEqual(rc, 1)
        r = load(rj)
        self.assertEqual(r["verdict"], "DOES_NOT_CONFORM")
        self.assertEqual([x["path"] for x in r["CHANGED"]], ["mods/alpha.py"])
        self.assertEqual([x["path"] for x in r["MISSING"]], ["laws/law1.txt"])
        self.assertEqual([x["path"] for x in r["EXTRA"]], ["mods/gamma.py"])
        self.assertEqual(sorted(x["path"] for x in r["MATCH"]),
                         ["README.md", "mods/beta.py", "sorter/order.json"])
        self.assertEqual(r["counts"], {"base_files": 5, "MATCH": 3, "CHANGED": 1,
                                       "MISSING": 1, "EXTRA": 1,
                                       "UNVERIFIED": 0, "SKIPPED": 2})
        check_sidecar(self, rj)

    def test_extra_only_conforms(self):
        box = self.copy_base("box_x")
        write(os.path.join(box, "local", "notes.txt"), b"seat notes\n")
        rj = os.path.join(self.tmp, "receipt_x.json")
        rc, _ = run(["check", self.base_json, box, "--box", "BOX-D", "--out", rj])
        r = load(rj)
        self.assertEqual(rc, 0)
        self.assertEqual(r["verdict"], "CONFORMS")
        self.assertEqual([x["path"] for x in r["EXTRA"]], ["local/notes.txt"])

    @unittest.skipUnless(hasattr(os, "symlink") and os.name != "nt",
                         "symlink test on POSIX only")
    def test_symlink_out_of_tree_not_followed(self):
        outside = os.path.join(self.tmp, "outside")
        write(os.path.join(outside, "secret.txt"), b"outside\n")
        box = self.copy_base("box_s")
        os.symlink(outside, os.path.join(box, "linkdir"))
        os.symlink(os.path.join(outside, "secret.txt"),
                   os.path.join(box, "linkfile.txt"))
        rj = os.path.join(self.tmp, "receipt_s.json")
        rc, _ = run(["check", self.base_json, box, "--box", "BOX-C",
                     "--out", rj])
        r = load(rj)
        self.assertEqual(r["verdict"], "CONFORMS")
        sk = {x["path"]: x["reason"] for x in r["SKIPPED"]}
        self.assertEqual(sk.get("linkdir"), "symlink or junction, not followed")
        self.assertEqual(sk.get("linkfile.txt"), "symlink or junction, not followed")
        self.assertNotIn("linkdir/secret.txt", [x["path"] for x in r["EXTRA"]])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs mkfifo")
    def test_sensitive_name_never_opened(self):
        # A FIFO blocks forever if opened. Named like a key, it must be skipped
        # by name before any open.
        box = self.copy_base("box_k")
        os.mkfifo(os.path.join(box, "ssh_key"))
        os.mkfifo(os.path.join(box, "Credentials.json"))
        os.mkfifo(os.path.join(box, "oauth.cfg"))
        rj = os.path.join(self.tmp, "receipt_k.json")
        rc, _ = run(["check", self.base_json, box, "--box", "BOX-B", "--out", rj])
        r = load(rj)
        sk = {x["path"]: x["reason"] for x in r["SKIPPED"]}
        for n in ("ssh_key", "Credentials.json", "oauth.cfg"):
            self.assertEqual(sk.get(n), "sensitive name, not opened", n)
        self.assertEqual(r["verdict"], "CONFORMS")

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "chmod 000 does not block reads as root or on Windows")
    def test_unreadable_file_listed(self):
        box = self.copy_base("box_u")
        p = os.path.join(box, "mods", "beta.py")
        os.chmod(p, 0)
        rj = os.path.join(self.tmp, "receipt_u.json")
        rc, _ = run(["check", self.base_json, box, "--box", "BOX-B", "--out", rj])
        r = load(rj)
        self.assertEqual([x["path"] for x in r["UNVERIFIED"]], ["mods/beta.py"])
        self.assertTrue(r["UNVERIFIED"][0]["reason"].startswith("unreadable"))
        self.assertEqual(r["verdict"], "DOES_NOT_CONFORM")
        self.assertEqual(rc, 1)

    def test_tampered_base_rejected(self):
        m = load(self.base_json)
        m["files"][0]["sha256"] = "0" * 64
        bad = os.path.join(self.tmp, "bad.json")
        with open(bad, "w") as f:
            json.dump(m, f)
        box = self.copy_base("box_t")
        rc, _ = run(["check", bad, box, "--box", "BOX-B",
                     "--out", os.path.join(self.tmp, "r_t.json")])
        self.assertEqual(rc, 2)

    def test_windows_style_base_paths(self):
        # A Base manifest written on BOX-A with backslash paths and no entries_sha256.
        m = load(self.base_json)
        for e in m["files"]:
            e["path"] = e["path"].replace("/", "\\")
        del m["entries_sha256"]
        win = os.path.join(self.tmp, "win.json")
        with open(win, "w") as f:
            json.dump(m, f)
        box = self.copy_base("box_w")
        rj = os.path.join(self.tmp, "r_w.json")
        rc, _ = run(["check", win, box, "--box", "BOX-A", "--out", rj])
        self.assertEqual(load(rj)["verdict"], "CONFORMS")
        self.assertEqual(rc, 0)

    @unittest.skipUnless(NP_MANIFEST and os.path.exists(NP_MANIFEST), "NP manifest copy not present")
    def test_np_manifest_parses(self):
        raw, obj, entries, notes = C.load_base(NP_MANIFEST)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "e605b853d6eea415073da043a65d9f28fb8b715e669d4ece94b0c74bee88e7b7")
        self.assertEqual(len(entries), obj["file_count"])
        self.assertTrue(all("\\" not in p for p in entries))


if __name__ == "__main__":
    unittest.main(verbosity=2)
