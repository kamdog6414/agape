#!/usr/bin/env python3
"""Agape round tool v0.2 (Conformance part, Work Order 3: offline perpetual hackathon).

Python 3 standard library only. No network. Plain monospace text output.

v0.2: packages are agape.mod.v0 (GPT Codex - MOD-SEAT, MOD-FORMAT.md).
Identity is the sha256 of the raw MANIFEST.json bytes, given as an external pin.
Verification is MOD-SEAT's package.verify_package(package_dir, expected_sha256);
payload code is never imported or run. Load order is SORTER-SEAT's
sorter.order_round(core, submissions, round_id), which feeds core.set_order.

v0.3: the founder's L-11 ruling. Round 0 stays on LAWS v1 (laws.py) as scorer of
record. Round 1 on judges with LAWS-SEAT's LAWS v2 (laws_v2.verify_point): the
round's own named-point manifest is hashed and its supersedes.sha256 links are
walked back to genesis NP-20261026T170000Z. close writes each new point as
<chain>/<NP id>/MANIFEST.json (folder-per-point) so the walk can find parents.
Conformance receipts get a round.py wrapper that records the round's real NP.

Commands (global --conformance <conformance.py> goes before the command):
  pack <moddir> --package <package.py> --id ID --version V --entry payload/x.py
       --inputs a,b --outputs c [--requires x,y] [--conflicts z] [--header H]
  open --np <named point id> --manifest <path> --out <rounddir> [--needs needs.json]
       [--laws-manifest <path>] [--chain <chain dir>]
  submit <rounddir> --mod <dir | .zip | .tgz | .tar> --sha256 <MANIFEST.json pin>
       --seat <DESIGNATION> [--member <dir inside archive>]
  judge <rounddir> --laws <laws.py> [--laws-v2 <laws_v2.py>] --package <package.py>
       --sorter <sorter.py> --base <base.py> [--box NAME] [--netns]
  conformance-check <base manifest> <dir> --box NAME --out <receipt> --np <NP id>
  chain <point MANIFEST.json> --laws-v2 <laws_v2.py> [--chain <chain dir>]
  close <rounddir>
  verify <rounddir> [--scratch DIR]

Exit codes: 0 = done / all PASS, 1 = done with a FAIL, 2 = error.
"""

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile

VERSION = "0.3"
TOOL = "agape-round v0.3"
HEADER = "Grok Bot - ROUND-SEAT"
ROUND_FORMAT = "agape.round.v0"
SUBMISSION_FORMAT = "agape.round.submission.v0.2"
SCORE_FORMAT = "agape.round.score.v0.3"
CONF_NP_FORMAT = "agape.round.conformance-np.v0"
CLOSE_FORMAT = "agape.round.close-manifest.v0"
NEEDS_FORMAT = "agape.round.needs.v0"
ORDER_FORMAT = "agape.round.order.v0.2"
MOD_SCHEMA = "agape.mod.v0"
GENESIS_NP = "NP-20261026T170000Z"
# Real genesis pin; AGAPE_GENESIS_SHA256 overrides it (public demo only).
GENESIS_SHA256 = os.environ.get("AGAPE_GENESIS_SHA256", "e605b853d6eea415073da043a65d9f28fb8b715e669d4ece94b0c74bee88e7b7")
CHAIN_DIRNAME = "chain"

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFORMANCE = os.path.join(os.path.dirname(HERE), "conformance",
                                   "conformance.py")
NETNS_ENV = "AGAPE_ROUND_IN_NETNS"
HOST_NETNS_ENV = "AGAPE_ROUND_HOST_NETNS"

# Plain words for each gate: what a FAIL shows we need.
NEED_TEXT = {
    "package_verify": "the package to pass MOD-SEAT verify_package against its "
                      "external MANIFEST.json pin (strict agape.mod.v0 manifest, "
                      "exact inventory, every payload size and sha256)",
    "named_point_hash": "a named-point manifest copy on the judging box that "
                        "hashes to the pinned point, or a laws pin that follows "
                        "the round chain",
    "no_secrets_in_mod": "the mod shipped without secret material; secrets stay "
                         "out of mods and in each box's own private store",
    "no_network": "the mod rebuilt with no network capability of its own; any "
                  "fetch goes through a named Agape part on the private network",
    "black_and_white": "the mod surface rebuilt in black and white only, with no "
                       "machine-readable color encodings",
    "conformance": "the package files to match the files[] list in its own "
                   "MANIFEST.json (no CHANGED, MISSING or UNVERIFIED entries)",
    "base_enable": "Base to accept the mod: a unique mod_id and a 64-hex "
                   "manifest sha256 (core.enable refused it)",
    "sorter": "a clear load order from Sorter: every requires id enabled in the "
              "round, no declared conflict pair, no cycle",
}
LAWS_NOT_RUN = "NOT_RUN"


# ---------------------------------------------------------------- helpers

def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def stamp(t):
    return t.strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def write_json(obj, path, sidecar=True):
    data = (json.dumps(obj, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    digest = sha256_bytes(data)
    if sidecar:
        write_sidecar(path, digest)
    return digest


def write_text(text, path, sidecar=True):
    data = text.encode("ascii", errors="replace")
    with open(path, "wb") as f:
        f.write(data)
    digest = sha256_bytes(data)
    if sidecar:
        write_sidecar(path, digest)
    return digest


def write_sidecar(path, digest):
    with open(path + ".sha256", "wb") as f:
        f.write(("%s  %s\n" % (digest, os.path.basename(path))).encode("ascii"))


def read_json(path):
    with open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8-sig"))


def load_module(name, path):
    if not path or not os.path.isfile(path):
        raise FileNotFoundError("module not found: %s" % path)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def round_json_path(rounddir):
    return os.path.join(rounddir, "round.json")


def load_round(rounddir):
    p = round_json_path(rounddir)
    if not os.path.isfile(p):
        raise ValueError("no round.json in %s" % rounddir)
    return read_json(p)


def save_round(rounddir, obj):
    return write_json(obj, round_json_path(rounddir))


def say(line=""):
    print(line)


def csv(value):
    return [x for x in (value or "").split(",") if x]


def module_pin(path):
    return {"path": os.path.abspath(path), "sha256": sha256_file(path)}


def load_laws_v2(path):
    """Load LAWS-SEAT laws_v2.py. It does `import laws` (its own v1 copy), so its
    folder goes on sys.path for the import only."""
    folder = os.path.dirname(os.path.abspath(path))
    sys.path.insert(0, folder)
    try:
        mod = load_module("agape_laws_v2_for_round", path)
    finally:
        sys.path.remove(folder)
    v1 = getattr(mod, "_v1", None)
    v1_file = getattr(v1, "__file__", None)
    return mod, ({"path": os.path.abspath(v1_file), "sha256": sha256_file(v1_file)}
                 if v1_file else None)


def chain_point_path(chain_dir, np_id):
    return os.path.join(chain_dir, np_id, "MANIFEST.json")


def place_in_chain(chain_dir, np_id, src_path):
    """Put a byte-exact copy of a point manifest at <chain>/<np>/MANIFEST.json.
    Refuses if a different file is already there. Returns its path."""
    dst = chain_point_path(chain_dir, np_id)
    want = sha256_file(src_path)
    if os.path.isfile(dst):
        if sha256_file(dst) != want:
            raise ValueError("chain already holds a different %s (%s)" % (dst, sha256_file(dst)))
        return dst
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.abspath(src_path) != os.path.abspath(dst):
        shutil.copyfile(src_path, dst)
    write_sidecar(dst, want)
    return dst


def chain_index(chain_dir):
    """sha256 -> path of every <chain>/<np>/MANIFEST.json, for evidence only."""
    idx = {}
    try:
        names = sorted(os.listdir(chain_dir))
    except OSError:
        return idx
    for n in names:
        p = os.path.join(chain_dir, n, "MANIFEST.json")
        if os.path.isfile(p):
            idx.setdefault(sha256_file(p), p)
    return idx


def conformance_check_np(conformance_py, base_manifest, target, box, out, np_id):
    """Run conformance.py check unchanged, then write <out minus .json>-np.json:
    a wrapper naming the round's real NP next to the NP the receipt stamped
    (conformance.py hardcodes NAMED_POINT). Returns (exit code, receipt or
    None, wrapper path or None, wrapper sha256 or None, raw output)."""
    proc = subprocess.run([sys.executable, conformance_py, "check", base_manifest,
                           target, "--box", box, "--out", out],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if not os.path.isfile(out):
        return proc.returncode, None, None, None, proc.stdout
    crec = read_json(out)
    stamped = crec.get("named_point")
    wrap = {
        "header": HEADER,
        "format": CONF_NP_FORMAT,
        "tool": TOOL,
        "named_point": np_id,
        "receipt_stamped_named_point": stamped,
        "np_matches_receipt": stamped == np_id,
        "conformance_receipt": {"path": os.path.abspath(out), "sha256": sha256_file(out)},
        "conformance_py": module_pin(conformance_py),
        "verdict": crec.get("verdict"),
        "note": "conformance.py stamps a constant NAMED_POINT; this wrapper is "
                "the round tool's --np record. Receipt bytes are unchanged.",
    }
    wpath = re.sub(r"\.json$", "", out) + "-np.json"
    wsha = write_json(wrap, wpath)
    return proc.returncode, crec, wpath, wsha, proc.stdout


# ---------------------------------------------------------------- pack

def cmd_pack(args):
    """Write an agape.mod.v0 MANIFEST.json (producer convention), then verify it
    with MOD-SEAT's verify_package. The pin goes outside the package."""
    pkg = load_module("agape_package_for_round", args.package)
    moddir = os.path.abspath(args.moddir)
    pdir = os.path.join(moddir, "payload")
    if not os.path.isdir(pdir):
        say("error: no payload/ folder in %s" % moddir)
        return 2
    files = []
    for base, dirs, names in os.walk(pdir):
        dirs.sort()
        for n in sorted(names):
            full = os.path.join(base, n)
            rel = os.path.relpath(full, moddir).replace(os.sep, "/")
            with open(full, "rb") as f:
                data = f.read()
            files.append({"path": rel, "bytes": len(data),
                          "sha256": sha256_bytes(data)})
    files.sort(key=lambda e: e["path"])
    manifest = {
        "header": args.header,
        "schema": MOD_SCHEMA,
        "mod_id": args.id,
        "version": args.version,
        "named_point": pkg.NAMED_POINT,
        "created_utc": iso(utc_now()),
        "base": dict(pkg.BASE),
        "entrypoint": {"path": args.entry, "callable": "run",
                       "protocol": "agape.mod.call.v0"},
        "runtime": dict(pkg.RUNTIME),
        "inputs": csv(args.inputs),
        "outputs": csv(args.outputs),
        "requires": sorted(csv(args.requires)),
        "conflicts": sorted(csv(args.conflicts)),
        "files": files,
    }
    raw = (json.dumps(manifest, ensure_ascii=True, sort_keys=True, indent=2,
                      allow_nan=False) + "\n").encode("utf-8")
    with open(os.path.join(moddir, "MANIFEST.json"), "wb") as f:
        f.write(raw)
    pin = sha256_bytes(raw)
    pin_path = moddir.rstrip("/") + ".MANIFEST.sha256"
    with open(pin_path, "wb") as f:
        f.write(("%s  %s/MANIFEST.json\n" % (pin, os.path.basename(moddir))).encode())
    try:
        res = pkg.verify_package(moddir, pin)
    except pkg.PackageError as e:
        say("FAIL pack: verify_package refused: %s" % e)
        return 1
    say("pack: %s  mod_id: %s  version: %s  files: %d" %
        (moddir, res["mod_id"], res["version"], res["file_count"]))
    say("MANIFEST.json sha256 (external pin): %s" % pin)
    say("pin file (outside the package): %s" % pin_path)
    say("verify_package: PASS")
    return 0


# ---------------------------------------------------------------- open

def next_round_number(manifest_obj):
    if isinstance(manifest_obj, dict) and manifest_obj.get("format") == CLOSE_FORMAT:
        rid = manifest_obj.get("round_id", "")
        m = re.fullmatch(r"R-(\d+)", rid)
        if not m:
            raise ValueError("close manifest has bad round_id: %r" % rid)
        return int(m.group(1)) + 1
    return 0


def cmd_open(args):
    if not os.path.isfile(args.manifest):
        say("error: manifest not found: %s" % args.manifest)
        return 2
    man_sha = sha256_file(args.manifest)
    try:
        man = read_json(args.manifest)
    except (ValueError, OSError) as e:
        say("error: manifest is not JSON: %s" % e)
        return 2
    np_in_file = (man.get("np_id") or man.get("name")) if isinstance(man, dict) else None
    if np_in_file and np_in_file != args.np:
        say("error: --np %s does not match the manifest's own id %s" %
            (args.np, np_in_file))
        return 2
    rnum = next_round_number(man)
    is_close = isinstance(man, dict) and man.get("format") == CLOSE_FORMAT
    if rnum == 0:
        # Round 0: LAWS v1 is scorer of record, pinned to the genesis manifest.
        laws_version = "v1"
        laws_manifest = os.path.abspath(args.laws_manifest or args.manifest)
        chain_dir = os.path.abspath(args.chain or os.path.join(
            os.path.dirname(os.path.abspath(args.out)), CHAIN_DIRNAME))
    else:
        # Round 1 on: LAWS v2 checks the round's OWN point and its chain.
        laws_version = "v2"
        if args.laws_manifest:
            say("error: --laws-manifest is for Round 0 only; from Round 1 on "
                "L-11 checks the round's own point (founder ruling, 11:02 PDT)")
            return 2
        mp = os.path.abspath(args.manifest)
        if args.chain:
            chain_dir = os.path.abspath(args.chain)
        elif (os.path.basename(mp) == "MANIFEST.json"
              and os.path.basename(os.path.dirname(mp)) == args.np):
            chain_dir = os.path.dirname(os.path.dirname(mp))
        else:
            chain_dir = os.path.join(os.path.dirname(os.path.abspath(args.out)),
                                     CHAIN_DIRNAME)
    if rnum == 0 and man_sha == GENESIS_SHA256:
        try:
            place_in_chain(chain_dir, args.np, args.manifest)
        except (ValueError, OSError) as e:
            say("error: %s" % e)
            return 2
    elif rnum > 0:
        try:
            laws_manifest = place_in_chain(chain_dir, args.np, args.manifest)
        except (ValueError, OSError) as e:
            say("error: %s" % e)
            return 2
    needs, needs_src = [], None
    if args.needs:
        nobj = read_json(args.needs)
        needs = list(nobj.get("needs", []))
        nsha = sha256_file(args.needs)
        needs_src = {"path": os.path.abspath(args.needs), "sha256": nsha}
        if is_close:
            want = man.get("needs_sha256")
            if want != nsha:
                say("error: needs file sha256 %s is not the one the close "
                    "manifest names (%s)" % (nsha, want))
                return 2
            needs_src["chained"] = True
    if os.path.exists(round_json_path(args.out)):
        say("error: round already open in %s" % args.out)
        return 2
    os.makedirs(os.path.join(args.out, "submissions"), exist_ok=True)
    t = utc_now()
    obj = {
        "header": HEADER,
        "format": ROUND_FORMAT,
        "tool": TOOL,
        "round_id": "R-%04d" % rnum,
        "status": "open",
        "named_point": args.np,
        "manifest": {"path": os.path.abspath(args.manifest), "sha256": man_sha,
                     "format": man.get("format") if isinstance(man, dict) else None},
        "laws_version": laws_version,
        "laws_manifest": laws_manifest,
        "chain_dir": chain_dir,
        "open_utc": iso(t),
        "needs_source": needs_src,
        "needs": needs,
        "submissions": [],
    }
    save_round(args.out, obj)
    say("open: %s  round: %s" % (args.out, obj["round_id"]))
    say("named point: %s" % args.np)
    say("manifest sha256: %s" % man_sha)
    say("laws: %s  L-11 manifest: %s" % (laws_version, laws_manifest))
    say("chain dir: %s" % chain_dir)
    say("open NEEDs: %d" % len(needs))
    for n in needs:
        say("  %s %s" % (n.get("id"), n.get("title", "")))
    return 0


# ---------------------------------------------------------------- submit

def _safe_member(name):
    n = name.replace("\\", "/")
    return not (n.startswith("/") or ".." in n.split("/") or re.match(r"^[A-Za-z]:", n))


def unpack_archive(pkg, dest):
    if zipfile.is_zipfile(pkg):
        with zipfile.ZipFile(pkg) as z:
            for n in z.namelist():
                if not _safe_member(n):
                    raise ValueError("unsafe archive member: %s" % n)
            z.extractall(dest)
        return "zip"
    if tarfile.is_tarfile(pkg):
        with tarfile.open(pkg) as t:
            for m in t.getmembers():
                if not _safe_member(m.name) or not (m.isfile() or m.isdir()):
                    raise ValueError("unsafe archive member: %s" % m.name)
            try:
                t.extractall(dest, filter="data")
            except TypeError:  # Python before 3.12 has no filter argument
                t.extractall(dest)
        return "tar"
    raise ValueError("not a directory, zip or tar: %s" % pkg)


def sensitive_names(conf, root):
    hits = []
    for base, dirs, names in os.walk(root):
        for n in dirs + names:
            if conf.is_sensitive(n):
                hits.append(os.path.relpath(os.path.join(base, n), root))
    return sorted(hits)


def cmd_submit(args):
    conf = load_module("agape_conformance_for_round", args.conformance)
    try:
        r = load_round(args.rounddir)
    except ValueError as e:
        say("error: %s" % e)
        return 2
    if r["status"] != "open":
        say("error: round %s is %s" % (r["round_id"], r["status"]))
        return 2
    if not args.seat or any(c.isspace() for c in args.seat):
        say("error: --seat must be one word")
        return 2
    if not re.fullmatch(r"[0-9a-f]{64}", args.sha256 or ""):
        say("error: --sha256 must be the 64 lowercase hex MANIFEST.json pin")
        return 2
    src = os.path.abspath(args.mod)
    staging = None
    archive = None
    try:
        if os.path.isdir(src):
            pkg_src = os.path.join(src, args.member) if args.member else src
            kind = "dir"
        elif os.path.isfile(src):
            staging = tempfile.mkdtemp(prefix="agape-round-submit-")
            kind = unpack_archive(src, staging)
            archive = {"path": src, "sha256": sha256_file(src), "kind": kind,
                       "member": args.member or ""}
            pkg_src = os.path.join(staging, args.member) if args.member else staging
        else:
            say("error: no such mod: %s" % src)
            return 2
        pkg_src = os.path.abspath(pkg_src)
        if not os.path.isdir(pkg_src) or not os.path.isfile(
                os.path.join(pkg_src, "MANIFEST.json")):
            say("error: no MANIFEST.json package folder at %s" % pkg_src)
            return 2
        bad = sensitive_names(conf, pkg_src)
        if bad:
            say("FAIL submit: sensitive file names, not copied or opened: %s" %
                ", ".join(bad))
            say("what this shows we need: package file names without key, "
                "token, auth or cred words")
            return 1
        sub_id = "S-%03d" % (len(r["submissions"]) + 1)
        sdir = os.path.join(args.rounddir, "submissions", sub_id)
        os.makedirs(sdir)
        pdir = os.path.join(sdir, "package")
        # Copy as is, links as links, so verify_package sees what was given.
        shutil.copytree(pkg_src, pdir, symlinks=True)
    finally:
        if staging:
            shutil.rmtree(staging, ignore_errors=True)
    raw_sha = sha256_file(os.path.join(pdir, "MANIFEST.json"))
    mod_id = version = schema = None
    try:
        m = read_json(os.path.join(pdir, "MANIFEST.json"))
        if isinstance(m, dict):
            mod_id, version, schema = m.get("mod_id"), m.get("version"), m.get("schema")
    except ValueError:
        pass
    rec = {
        "header": HEADER,
        "format": SUBMISSION_FORMAT,
        "round_id": r["round_id"],
        "submission_id": sub_id,
        "seat": args.seat,
        "submitted_utc": iso(utc_now()),
        "source": src,
        "archive": archive,
        "package_dir": os.path.relpath(pdir, args.rounddir),
        "schema": schema,
        "mod_id": mod_id,
        "version": version,
        "external_pin_sha256": args.sha256,
        "manifest_sha256_observed": raw_sha,
        "pin_matches_at_submit": raw_sha == args.sha256,
        "note": "identity is sha256 of raw MANIFEST.json bytes (agape.mod.v0); "
                "judge runs verify_package against the external pin",
    }
    rec_sha = write_json(rec, os.path.join(sdir, "submission.json"))
    r["submissions"].append({"submission_id": sub_id, "seat": args.seat,
                             "mod_id": mod_id, "version": version,
                             "external_pin_sha256": args.sha256,
                             "submission_sha256": rec_sha})
    save_round(args.rounddir, r)
    say("submit: %s %s  seat: %s  mod: %s %s  schema: %s" %
        (r["round_id"], sub_id, args.seat, mod_id, version, schema))
    say("external pin:            %s" % args.sha256)
    say("MANIFEST.json observed:  %s  %s" %
        (raw_sha, "match" if raw_sha == args.sha256 else "MISMATCH"))
    if archive:
        say("archive: %s  sha256: %s  member: %s" %
            (archive["path"], archive["sha256"], archive["member"] or "."))
    return 0


# ---------------------------------------------------------------- offline evidence

def _read_proc(path):
    try:
        with open(path, "r", encoding="ascii", errors="replace") as f:
            return f.read()
    except OSError as e:
        return "UNREADABLE: %s" % type(e).__name__


def offline_evidence(unshare_note):
    """Namespace-aware network evidence from inside this run: /proc/self/ns/net,
    /proc/net/dev and /proc/net/route. /sys/class/net is not used (a host sysfs
    mount does not enumerate a child namespace)."""
    try:
        netns = os.readlink("/proc/self/ns/net")
    except OSError as e:
        netns = "UNREADABLE: %s" % type(e).__name__
    host = os.environ.get(HOST_NETNS_ENV, "")
    dev = _read_proc("/proc/net/dev")
    route = _read_proc("/proc/net/route")
    ifaces = {}
    for line in dev.splitlines()[2:]:
        if ":" in line:
            name, rest = line.split(":", 1)
            nums = rest.split()
            ifaces[name.strip()] = {"rx_bytes": int(nums[0]) if nums else None,
                                    "tx_bytes": int(nums[8]) if len(nums) > 8 else None}
    routes = [ln for ln in route.splitlines()[1:] if ln.strip()]
    non_lo = sorted(n for n in ifaces if n != "lo")
    in_child = bool(os.environ.get(NETNS_ENV)) and bool(host) and netns != host
    offline = in_child and not non_lo and not routes
    lines = [
        "offline run evidence (namespace-aware)",
        "source: /proc/self/ns/net, /proc/net/dev, /proc/net/route read inside this run",
        "not used: /sys/class/net (host sysfs view, does not show a child namespace)",
        "unshare: %s" % unshare_note,
        "host netns:  %s" % (host or "unknown (not re-executed)"),
        "run netns:   %s" % netns,
        "interfaces:  %s" % (", ".join(sorted(ifaces)) or "none"),
        "non-lo interfaces: %s" % (", ".join(non_lo) or "none"),
        "route rows:  %d" % len(routes),
        "verdict: %s" % ("OFFLINE_NAMESPACE" if offline else "NOT_PROVEN_OFFLINE"),
        "",
        "--- /proc/net/dev",
        dev.rstrip("\n"),
        "--- /proc/net/route",
        route.rstrip("\n"),
    ]
    summary = {"unshare": unshare_note, "host_netns": host or None,
               "run_netns": netns, "interfaces": sorted(ifaces),
               "non_lo_interfaces": non_lo, "route_rows": len(routes),
               "verdict": "OFFLINE_NAMESPACE" if offline else "NOT_PROVEN_OFFLINE"}
    return summary, "\n".join(lines) + "\n"


def maybe_reexec_in_netns(argv):
    """With --netns, re-run this same judge under `unshare -rn`. Returns an exit
    code if it re-executed, or (None, note) to run here."""
    if os.environ.get(NETNS_ENV):
        return None, os.environ.get("AGAPE_ROUND_UNSHARE_NOTE", "unshare -rn")
    exe = shutil.which("unshare")
    if not exe:
        return None, "unshare not available on this box; judged in the host namespace"
    probe = subprocess.run([exe, "-rn", "true"], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
    if probe.returncode != 0:
        return None, ("unshare -rn refused (%s); judged in the host namespace" %
                      probe.stdout.decode("ascii", "replace").strip())
    env = dict(os.environ)
    env[NETNS_ENV] = "1"
    env[HOST_NETNS_ENV] = os.readlink("/proc/self/ns/net")
    env["AGAPE_ROUND_UNSHARE_NOTE"] = "%s -rn (user + network namespace), worked" % exe
    cmd = [exe, "-rn", sys.executable, os.path.abspath(__file__)] + argv
    return subprocess.run(cmd, env=env).returncode, None


# ---------------------------------------------------------------- judge

def law_evidence(laws, name, root, manifest_path, v2=None):
    """Run one laws predicate by its real name; return (ok, text lines, extra).
    v2 = {"open_sha256", "chain_dir"} selects LAWS v2 for named_point_hash."""
    extra = None
    if v2 is not None:
        lines = ["law: %s" % name, "laws: v2 (laws_v2.py, LAWS-SEAT)",
                 "genesis: %s %s" % (laws.GENESIS_POINT, laws.GENESIS_MANIFEST_SHA256)]
    else:
        lines = ["law: %s" % name, "laws: v1 (laws.py), named point: %s" %
                 getattr(laws, "NAMED_POINT", "?")]
    if name == "named_point_hash" and v2 is not None:
        vp = laws.verify_point(manifest_path, [v2["chain_dir"]])
        pin_ok = vp["manifest_sha256"] == v2["open_sha256"]
        ok = bool(vp["verdict"]) and pin_ok
        reason = vp["reason"]
        if vp["verdict"] and not pin_ok:
            reason = ("round manifest changed since open: now %s, round.json "
                      "pinned %s" % (vp["manifest_sha256"], v2["open_sha256"]))
        idx = chain_index(v2["chain_dir"])
        lines += ["round manifest: %s" % manifest_path,
                  "round manifest sha256: %s" % vp["manifest_sha256"],
                  "round.json open pin:   %s  %s" % (v2["open_sha256"],
                                                     "match" if pin_ok else "MISMATCH"),
                  "point: %s" % vp["point"],
                  "chain dir (search_dirs): %s" % v2["chain_dir"],
                  "depth: %d" % vp["depth"],
                  "laws_v2 verdict: %s" % vp["verdict"],
                  "reason: %s" % reason]
        for i, h in enumerate(vp["chain"]):
            lines.append("chain[%d]: %s  %s" % (i, h, idx.get(h, "(not in chain dir)")))
        broken = None
        if not vp["verdict"] and vp["chain"]:
            last = idx.get(vp["chain"][-1]) or (manifest_path if len(vp["chain"]) == 1 else None)
            try:
                sup = read_json(last).get("supersedes") if last else None
            except (ValueError, OSError, AttributeError):
                sup = None
            if isinstance(sup, dict):
                broken = {"at": len(vp["chain"]) - 1, "supersedes_sha256": sup.get("sha256"),
                          "supersedes_np_id": sup.get("np_id")}
                lines.append("broken link: chain[%d] supersedes %s %s; no manifest in "
                             "the chain dir hashes to it" %
                             (broken["at"], broken["supersedes_np_id"],
                              broken["supersedes_sha256"]))
        extra = dict(vp, open_pin_matches=pin_ok, reason_round=reason,
                     chain_dir=v2["chain_dir"], broken_link=broken)
    elif name == "named_point_hash":
        ok = bool(laws.named_point_hash(manifest_path))
        try:
            got = sha256_file(manifest_path)
        except OSError:
            got = "unreadable"
        lines += ["manifest: %s" % manifest_path, "manifest sha256: %s" % got,
                  "pin: %s" % laws.NAMED_POINT_MANIFEST_SHA256]
    elif name == "no_secrets_in_mod":
        ok = bool(laws.no_secrets_in_mod(root))
        lines += ["hit (path only, never values): %s" % h for h in laws.secret_hits(root)]
    elif name == "no_network":
        ok = bool(laws.no_network(root))
        lines += ["hit: %s" % h for h in laws.network_hits(root)]
    elif name == "black_and_white":
        ok = bool(laws.black_and_white(root))
        lines += ["hit: %s" % h for h in laws.color_hits(root)]
    else:
        ok = bool(getattr(laws, name)(root))
    lines.insert(1, "result: %s" % ("PASS" if ok else "FAIL"))
    lines.append("scanned: %s" % root)
    return ok, lines, extra


def cmd_judge(args, argv):
    if args.netns:
        code, note = maybe_reexec_in_netns(argv)
        if code is not None:
            return code
    else:
        note = "not requested (--netns not given); judged in the host namespace"
    try:
        r = load_round(args.rounddir)
        laws_v1 = load_module("agape_laws_for_round", args.laws)
        laws_version = r.get("laws_version") or (
            "v1" if r["round_id"] == "R-0000" else "v2")
        laws_v2 = v2_imported = None
        if laws_version == "v2":
            if not args.laws_v2:
                say("error: %s is a LAWS v2 round; give --laws-v2 laws_v2.py" %
                    r["round_id"])
                return 2
            laws_v2, v2_imported = load_laws_v2(args.laws_v2)
        laws = laws_v2 if laws_v2 else laws_v1
        pkg = load_module("agape_package_for_round", args.package)
        sorter = load_module("agape_sorter_for_round", args.sorter)
        base = load_module("agape_base_for_round", args.base)
    except (ValueError, OSError) as e:
        say("error: %s" % e)
        return 2
    if r["status"] != "open":
        say("error: round %s is %s" % (r["round_id"], r["status"]))
        return 2
    predicates = list(laws.PREDICATES)
    pins = {"laws_version": laws_version,
            "laws_py": module_pin(args.laws), "package_py": module_pin(args.package),
            "sorter_py": module_pin(args.sorter), "base_py": module_pin(args.base),
            "conformance_py": module_pin(args.conformance)}
    v2ctx = None
    if laws_v2:
        pins["laws_v2_py"] = module_pin(args.laws_v2)
        pins["laws_v2_imports_v1"] = v2_imported
        v2ctx = {"open_sha256": r["manifest"]["sha256"],
                 "chain_dir": r.get("chain_dir") or os.path.join(
                     os.path.dirname(os.path.abspath(args.rounddir)), CHAIN_DIRNAME)}
    edir_root = os.path.join(args.rounddir, "evidence")
    os.makedirs(edir_root, exist_ok=True)
    off_summary, off_text = offline_evidence(note)
    off_path = os.path.join(edir_root, "run-offline.txt")
    off_sha = write_text(off_text, off_path)
    off_row = dict(off_summary, evidence_path=os.path.relpath(off_path, args.rounddir),
                   evidence_sha256=off_sha)

    rows = []
    for s in r["submissions"]:
        sid = s["submission_id"]
        sdir = os.path.join(args.rounddir, "submissions", sid)
        pdir = os.path.abspath(os.path.join(sdir, "package"))
        edir = os.path.join(edir_root, sid)
        os.makedirs(edir, exist_ok=True)
        sub = read_json(os.path.join(sdir, "submission.json"))
        # 1. verify_package against the external pin. Read-only, no payload import.
        try:
            verified = pkg.verify_package(pdir, sub["external_pin_sha256"])
            v_ok, v_lines = True, ["verify_package: PASS"] + [
                "%s: %s" % (k, json.dumps(verified[k], sort_keys=True))
                for k in sorted(verified)]
        except pkg.PackageError as e:
            verified, v_ok, v_lines = None, False, ["verify_package: FAIL",
                                                     "PackageError: %s" % e]
        v_lines = ["package: %s" % pdir, "external pin: %s" %
                   sub["external_pin_sha256"]] + v_lines
        vp = os.path.join(edir, "package_verify.txt")
        v_row = {"result": "PASS" if v_ok else "FAIL",
                 "evidence_path": os.path.relpath(vp, args.rounddir),
                 "evidence_sha256": write_text("\n".join(v_lines) + "\n", vp),
                 "verified": verified}
        # 2. laws, only over a verified package (unverified bytes are not scanned)
        law_rows, passed = {}, []
        for name in predicates:
            extra = None
            if v_ok or name == "named_point_hash":
                ok, lines, extra = law_evidence(laws, name, pdir, r["laws_manifest"],
                                                v2ctx)
            else:
                ok, lines = False, ["law: %s" % name, "result: %s" % LAWS_NOT_RUN,
                                    "package failed verify_package; payload not scanned"]
            ep = os.path.join(edir, "%s.txt" % name)
            res = "PASS" if ok else ("FAIL" if (v_ok or name == "named_point_hash")
                                     else LAWS_NOT_RUN)
            law_rows[name] = {"result": res,
                              "evidence_path": os.path.relpath(ep, args.rounddir),
                              "evidence_sha256": write_text("\n".join(lines) + "\n", ep)}
            if extra is not None:
                law_rows[name]["point_verification"] = extra
                law_rows[name]["reason"] = extra["reason_round"]
            if ok:
                passed.append(name)
        # 3. conformance: the package's own MANIFEST.json files[] is the base
        cp = os.path.join(edir, "conformance.json")
        c_rc, crec, wpath, wsha, c_out = conformance_check_np(
            args.conformance, os.path.join(pdir, "MANIFEST.json"), pdir, args.box,
            cp, r["named_point"])
        if crec is not None:
            conf_row = {"verdict": crec.get("verdict"), "exit_code": c_rc,
                        "named_point": r["named_point"],
                        "receipt_stamped_named_point": crec.get("named_point"),
                        "np_wrapper_path": os.path.relpath(wpath, args.rounddir),
                        "np_wrapper_sha256": wsha,
                        "counts": crec.get("counts"),
                        "notes": crec.get("base_manifest", {}).get("notes"),
                        "receipt_path": os.path.relpath(cp, args.rounddir),
                        "receipt_sha256": sha256_file(cp),
                        "base_manifest": "submissions/%s/package/MANIFEST.json" % sid}
        else:
            conf_row = {"verdict": "ERROR", "exit_code": c_rc,
                        "output": c_out.decode("ascii", "replace")[-2000:]}
        gate = v_ok and len(passed) == len(predicates) and conf_row["verdict"] == "CONFORMS"
        rows.append({"s": s, "sub": sub, "verified": verified, "v_row": v_row,
                     "laws": law_rows, "passed": passed, "conf": conf_row,
                     "gate": gate})

    # 4. one round core on this box: enable gated mods, then Sorter orders them
    core = base.open_base(args.box)
    for row in rows:
        row["enable"] = None
        if row["gate"]:
            row["enable"] = core.enable(row["verified"]["mod_id"],
                                        row["verified"]["manifest_sha256"])
    enabled_rows = [row for row in rows if row["enable"]
                    and row["enable"]["result"] == "enabled"]
    order = sorter.order_round(core, [row["verified"] for row in enabled_rows],
                               r["round_id"])
    if enabled_rows and order["result"] == "clear":
        note_receipt = core.note_laws(predicates)
    else:
        note_receipt = None
    order_rec = {
        "header": HEADER, "format": ORDER_FORMAT, "round_id": r["round_id"],
        "box": args.box, "ordered_utc": iso(utc_now()),
        "sorter_py": pins["sorter_py"],
        "input": [{"submission_id": row["s"]["submission_id"],
                   "mod_id": row["verified"]["mod_id"],
                   "requires": row["verified"]["requires"],
                   "conflicts": row["verified"]["conflicts"]} for row in enabled_rows],
        "not_offered": [{"submission_id": row["s"]["submission_id"],
                         "reason": "failed an earlier gate" if not row["gate"]
                         else "core.enable refused"}
                        for row in rows if row not in enabled_rows],
        "order_round": order,
        "note_laws": note_receipt,
        "base_receipts": core.receipts(),
        "probe": core.probe(),
    }
    op = os.path.join(edir_root, "order.json")
    o_sha = write_json(order_rec, op)

    any_fail = False
    for row in rows:
        s, sub, sid = row["s"], row["sub"], row["s"]["submission_id"]
        mid = row["verified"]["mod_id"] if row["verified"] else sub.get("mod_id")
        en_ok = bool(row["enable"]) and row["enable"]["result"] == "enabled"
        ids = order.get("ids") or []
        so_ok = en_ok and order["result"] == "clear" and mid in ids
        if not row["gate"]:
            so_res, en_res = "NOT_RUN", "NOT_RUN"
        else:
            en_res = "PASS" if en_ok else "FAIL"
            so_res = "PASS" if so_ok else ("FAIL" if en_ok else "NOT_RUN")
        overall = row["gate"] and en_ok and so_ok
        score = {
            "header": HEADER,
            "format": SCORE_FORMAT,
            "tool": TOOL,
            "round_id": r["round_id"],
            "named_point": r["named_point"],
            "laws_version": laws_version,
            "submission_id": sid,
            "seat": s["seat"],
            "mod_id": mid,
            "version": row["verified"]["version"] if row["verified"] else sub.get("version"),
            "manifest_sha256": sub["manifest_sha256_observed"],
            "external_pin_sha256": sub["external_pin_sha256"],
            "judged_utc": iso(utc_now()),
            "pins": pins,
            "run_offline": off_row,
            "package_verify": row["v_row"],
            "laws": row["laws"],
            "conformance": row["conf"],
            "base_enable": {"result": en_res, "receipt": row["enable"]},
            "sorter": {"result": so_res, "order_round_result": order["result"],
                       "ids": order.get("ids"), "conflicts": order.get("conflicts"),
                       "position": (ids.index(mid) + 1) if so_ok else None,
                       "evidence_path": os.path.relpath(op, args.rounddir),
                       "evidence_sha256": o_sha},
            "overall": "PASS" if overall else "FAIL",
            "overall_rule": "PASS only if package_verify, all four laws, "
                            "conformance CONFORMS, base_enable and sorter all PASS",
        }
        spath = os.path.join(args.rounddir, "score-%s.json" % sid)
        ssha = write_json(score, spath)
        s["score"] = {"path": os.path.basename(spath), "sha256": ssha,
                      "overall": score["overall"]}
        row["score"] = score
        any_fail = any_fail or not overall
    r["judged_utc"] = iso(utc_now())
    r["judge"] = {"tool": TOOL, "box": args.box, "pins": pins,
                  "run_offline": off_row,
                  "order": {"path": os.path.relpath(op, args.rounddir), "sha256": o_sha,
                            "result": order["result"], "ids": order.get("ids")}}
    save_round(args.rounddir, r)

    say("judge: %s  submissions: %d  box: %s  laws: %s" %
        (r["round_id"], len(rows), args.box, laws_version))
    say("offline: %s  run netns %s  host netns %s" %
        (off_row["verdict"], off_row["run_netns"], off_row["host_netns"]))
    say("         interfaces %s  routes %d  (%s)" %
        (",".join(off_row["interfaces"]) or "none", off_row["route_rows"], note))
    for row in rows:
        sc = row["score"]
        say("%s  seat %s  mod %s %s  overall %s" %
            (sc["submission_id"], sc["seat"], sc["mod_id"], sc["version"], sc["overall"]))
        say("  %-18s %s" % ("package_verify", sc["package_verify"]["result"]))
        for name in predicates:
            pv = sc["laws"][name].get("point_verification")
            say("  %-18s %s%s" % (name, sc["laws"][name]["result"],
                                  ("  depth %d  reason: %s" % (pv["depth"], pv["reason_round"]))
                                  if pv else ""))
        say("  %-18s %s" % ("conformance", sc["conformance"]["verdict"]))
        say("  %-18s %s" % ("base_enable", sc["base_enable"]["result"]))
        say("  %-18s %s  position %s" % ("sorter", sc["sorter"]["result"],
                                         sc["sorter"]["position"]))
        say("  score sha256 %s" % row["s"]["score"]["sha256"])
    say("sorter order_round: %s  ids %s  conflicts %s  applied %s" %
        (order["result"], order.get("ids"), json.dumps(order.get("conflicts")),
         order.get("applied")))
    return 1 if any_fail else 0


# ---------------------------------------------------------------- close

def score_fails(score):
    fails = []
    if score["package_verify"]["result"] != "PASS":
        fails.append(("package_verify", score["package_verify"]))
        return fails  # laws/conformance on unverified bytes are not separate NEEDs
    for k, v in score["laws"].items():
        if v["result"] != "PASS":
            fails.append((k, v))
    if score["conformance"]["verdict"] != "CONFORMS":
        fails.append(("conformance", {
            "evidence_path": score["conformance"].get("receipt_path"),
            "evidence_sha256": score["conformance"].get("receipt_sha256")}))
    if score["base_enable"]["result"] == "FAIL":
        fails.append(("base_enable", {}))
    if score["sorter"]["result"] == "FAIL":
        fails.append(("sorter", score["sorter"]))
    return fails


def cmd_close(args):
    conf = load_module("agape_conformance_for_round", args.conformance)
    try:
        r = load_round(args.rounddir)
    except ValueError as e:
        say("error: %s" % e)
        return 2
    if r["status"] != "open":
        say("error: round %s is %s" % (r["round_id"], r["status"]))
        return 2
    unjudged = [s["submission_id"] for s in r["submissions"] if "score" not in s]
    if unjudged:
        say("error: not judged yet: %s" % ", ".join(unjudged))
        return 2
    needs = [dict(n, carried_from=n.get("carried_from") or r["round_id"])
             for n in r.get("needs", [])]
    num = 0
    for n in needs:
        m = re.fullmatch(r"N-(\d+)", n.get("id", ""))
        if m:
            num = max(num, int(m.group(1)))
    new = []
    for s in r["submissions"]:
        score = read_json(os.path.join(args.rounddir, s["score"]["path"]))
        for law, row in score_fails(score):
            num += 1
            new.append({
                "id": "N-%03d" % num,
                "status": "open",
                "title": "FAIL %s on %s %s (%s)" % (law, s["submission_id"],
                                                    score.get("mod_id"), s["seat"]),
                "what_this_shows_we_need": NEED_TEXT.get(law, "the %s check to pass" % law),
                "from_round": r["round_id"],
                "from_part": s["seat"],
                "law": law,
                "evidence_path": row.get("evidence_path"),
                "evidence_sha256": row.get("evidence_sha256"),
                "score_path": s["score"]["path"],
                "score_sha256": s["score"]["sha256"],
            })
    chain_dir = r.get("chain_dir") or os.path.join(
        os.path.dirname(os.path.abspath(args.rounddir)), CHAIN_DIRNAME)
    t = utc_now()
    # NP ids are second-stamped; never reuse one the chain already holds.
    while os.path.exists(os.path.join(chain_dir, "NP-%s" % stamp(t))):
        time.sleep(0.25)
        t = utc_now()
    np_id = "NP-%s" % stamp(t)
    cdir = os.path.join(args.rounddir, "close")
    os.makedirs(cdir, exist_ok=True)
    r["status"] = "closed"
    r["close_utc"] = iso(t)
    r["closed_as"] = np_id
    save_round(args.rounddir, r)
    needs_obj = {"header": HEADER, "format": NEEDS_FORMAT,
                 "from_round": r["round_id"], "from_named_point": np_id,
                 "needs": needs + new}
    needs_path = os.path.join(cdir, "needs.json")
    needs_sha = write_json(needs_obj, needs_path)
    man_path = os.path.join(cdir, "%s.json" % np_id)
    files, skipped = conf.walk_tree(args.rounddir, (man_path, man_path + ".sha256"))
    prev_chain = chain_point_path(chain_dir, r["named_point"])
    if not os.path.isfile(prev_chain) and r["manifest"]["sha256"] == GENESIS_SHA256:
        place_in_chain(chain_dir, r["named_point"], r["manifest"]["path"])
    man = {
        "header": HEADER, "format": CLOSE_FORMAT, "tool": TOOL,
        "name": np_id,
        "np_id": np_id, "point_utc": iso(t), "round_id": r["round_id"],
        "supersedes": {"sha256": r["manifest"]["sha256"],
                       "np_id": r["named_point"],
                       "path": prev_chain,
                       "note": "parent named point (LAWS v2 chain link)"},
        "root": os.path.abspath(args.rounddir),
        "prev_np_id": r["named_point"],
        "prev_manifest_sha256": r["manifest"]["sha256"],
        "prev_manifest_path": r["manifest"]["path"],
        "laws_manifest": r["laws_manifest"],
        "laws_version": r.get("laws_version") or "v1",
        "chain_dir": chain_dir,
        "needs_path": os.path.relpath(needs_path, args.rounddir),
        "needs_sha256": needs_sha,
        "path_separator": "/",
        "file_count": len(files),
        "total_bytes": sum(e["bytes"] for e in files),
        "entries_hash_method": "sha256 of JSON array of {path,bytes,sha256} "
                               "sorted by path, sort_keys, separators (',',':'), UTF-8",
        "entries_sha256": conf.entries_hash(files),
        "files": files,
        "excluded": skipped,
    }
    man_sha = write_json(man, man_path)
    chain_copy = place_in_chain(chain_dir, np_id, man_path)
    say("close: %s  as %s" % (r["round_id"], np_id))
    say("chain point: %s" % chain_copy)
    say("supersedes: %s  %s" % (r["named_point"], r["manifest"]["sha256"]))
    say("manifest: %s" % man_path)
    say("manifest sha256: %s" % man_sha)
    say("prev: %s  %s" % (r["named_point"], r["manifest"]["sha256"]))
    say("files: %d  entries_sha256: %s" % (len(files), man["entries_sha256"]))
    say("needs: %s  sha256: %s" % (needs_path, needs_sha))
    for n in needs + new:
        say("  %s %s" % (n["id"], n["title"]))
        say("    what this shows we need: %s" % n["what_this_shows_we_need"])
    say("next: round.py open --np %s --manifest %s --needs %s --out <rounddir>" %
        (np_id, chain_copy, needs_path))
    return 0


# ---------------------------------------------------------------- verify

def cmd_verify(args):
    """Re-check a closed round dir against its close manifest, and the chain link."""
    r = load_round(args.rounddir)
    if r["status"] != "closed":
        say("FAIL verify: round %s is %s" % (r["round_id"], r["status"]))
        return 1
    man_path = os.path.join(args.rounddir, "close", "%s.json" % r["closed_as"])
    man = read_json(man_path)
    with open(man_path + ".sha256") as f:
        side = f.read().split()[0]
    got = sha256_file(man_path)
    ok = got == side
    say("%s manifest sha256 %s sidecar %s" % ("PASS" if ok else "FAIL", got, side))
    link = man["prev_manifest_sha256"] == r["manifest"]["sha256"]
    say("%s chain link %s -> %s" % ("PASS" if link else "FAIL", r["closed_as"],
                                    man["prev_np_id"]))
    ok = ok and link
    os.makedirs(args.scratch, exist_ok=True)
    out = os.path.join(args.scratch, "verify-%s.json" % r["round_id"])
    _rc, crec, _w, _ws, _o = conformance_check_np(
        args.conformance, man_path, args.rounddir, "ROUND-VERIFY", out, r["closed_as"])
    verdict = crec.get("verdict") if crec else "ERROR"
    say("%s conformance of round dir against close manifest: %s" %
        ("PASS" if verdict == "CONFORMS" else "FAIL", verdict))
    ok = ok and verdict == "CONFORMS"
    return 0 if ok else 1


# ---------------------------------------------------------------- conformance-check, chain

def cmd_conformance_check(args):
    rc, crec, wpath, wsha, out = conformance_check_np(
        args.conformance, args.base, args.dir, args.box, args.out, args.np)
    if crec is None:
        sys.stdout.write(out.decode("ascii", "replace"))
        return 2
    say("conformance: %s  receipt %s" % (crec.get("verdict"), args.out))
    say("np: %s  (receipt stamped %s)" % (args.np, crec.get("named_point")))
    say("np wrapper: %s  sha256 %s" % (wpath, wsha))
    return rc


def cmd_chain(args):
    laws_v2, _ = load_laws_v2(args.laws_v2)
    chain_dir = os.path.abspath(args.chain or os.path.dirname(
        os.path.dirname(os.path.abspath(args.manifest))))
    vp = laws_v2.verify_point(args.manifest, [chain_dir])
    idx = chain_index(chain_dir)
    say("point: %s  verdict: %s  depth: %d  reason: %s" %
        (vp["point"], "PASS" if vp["verdict"] else "FAIL", vp["depth"], vp["reason"]))
    for i, h in enumerate(vp["chain"]):
        say("  chain[%d] %s  %s" % (i, h, idx.get(h, "(not in chain dir)")))
    return 0 if vp["verdict"] else 1


# ---------------------------------------------------------------- main

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="round.py", description=TOOL)
    ap.add_argument("--conformance", default=DEFAULT_CONFORMANCE,
                    help="path to conformance.py (default %(default)s)")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("pack", help="write an agape.mod.v0 MANIFEST.json and verify it")
    p.add_argument("moddir")
    p.add_argument("--package", required=True, help="MOD-SEAT package.py")
    p.add_argument("--id", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--entry", required=True, help="payload/<file>.py with run()")
    p.add_argument("--inputs", required=True)
    p.add_argument("--outputs", required=True)
    p.add_argument("--requires", default="")
    p.add_argument("--conflicts", default="")
    p.add_argument("--header", default=HEADER)

    o = sub.add_parser("open", help="open a round from a named point")
    o.add_argument("--np", required=True)
    o.add_argument("--manifest", required=True)
    o.add_argument("--out", required=True)
    o.add_argument("--needs")
    o.add_argument("--laws-manifest", help="Round 0 only")
    o.add_argument("--chain", help="chain dir of <NP id>/MANIFEST.json points")

    s = sub.add_parser("submit", help="record an agape.mod.v0 package submission")
    s.add_argument("rounddir")
    s.add_argument("--mod", required=True)
    s.add_argument("--sha256", required=True, help="external MANIFEST.json pin")
    s.add_argument("--seat", required=True)
    s.add_argument("--member", help="package folder inside the archive or dir")

    j = sub.add_parser("judge", help="verify, laws, conformance, enable, sort")
    j.add_argument("rounddir")
    j.add_argument("--laws", required=True, help="laws.py (v1, Round 0 scorer of record)")
    j.add_argument("--laws-v2", help="LAWS-SEAT laws_v2.py (Round 1 on)")
    j.add_argument("--package", required=True, help="MOD-SEAT package.py")
    j.add_argument("--sorter", required=True, help="SORTER-SEAT sorter.py")
    j.add_argument("--base", required=True, help="base.py (agape.base.v0)")
    j.add_argument("--box", default="ROUND-SEAT", help="box name for open_base")
    j.add_argument("--netns", action="store_true",
                   help="re-run the judge under unshare -rn and record /proc/net evidence")

    k = sub.add_parser("conformance-check", help="conformance.py check plus an --np record")
    k.add_argument("base")
    k.add_argument("dir")
    k.add_argument("--box", required=True)
    k.add_argument("--out", required=True)
    k.add_argument("--np", required=True)

    w = sub.add_parser("chain", help="walk a point's supersedes links with laws_v2")
    w.add_argument("manifest")
    w.add_argument("--laws-v2", required=True)
    w.add_argument("--chain")

    c = sub.add_parser("close", help="stamp a new named point and write NEEDs")
    c.add_argument("rounddir")

    v = sub.add_parser("verify", help="re-check a closed round")
    v.add_argument("rounddir")
    v.add_argument("--scratch", default=os.path.join(tempfile.gettempdir(), "agape-round-verify"))

    args = ap.parse_args(argv)
    if args.cmd == "judge":
        return cmd_judge(args, argv)
    fn = {"pack": cmd_pack, "open": cmd_open, "submit": cmd_submit,
          "close": cmd_close, "verify": cmd_verify, "chain": cmd_chain,
          "conformance-check": cmd_conformance_check}.get(args.cmd)
    if fn is None:
        ap.print_help()
        return 2
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
