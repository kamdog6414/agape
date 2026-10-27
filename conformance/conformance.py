#!/usr/bin/env python3
"""Agape Conformance checker v0.

Python 3 standard library only. Runs on Windows, Linux, and macOS.

Commands:
  manifest <dir> --out base.json
  check <base.json> <dir> --box <designation> --out receipt.json

Exit codes: 0 = done (manifest written, or verdict CONFORMS),
            1 = verdict DOES_NOT_CONFORM, 2 = error.
"""

import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import stat
import sys

TOOL = "agape-conformance v0"
HEADER = "Grok Bot - ROUND-SEAT"
NAMED_POINT = "NP-20261026T170000Z"
MANIFEST_FORMAT = "agape.conformance.base-manifest.v0"
RECEIPT_FORMAT = "agape.conformance.receipt.v0"

# File names matching these patterns are never opened, read, or hashed.
# Match is on the file name only (not the directory), case-insensitive.
SENSITIVE_PATTERNS = ["*token*", "*key*", "*auth*", "*cred*", "*.env"]

CHUNK = 1024 * 1024


def is_sensitive(name):
    low = name.lower()
    return any(fnmatch.fnmatchcase(low, p) for p in SENSITIVE_PATTERNS)


def norm_rel(path):
    """Normalize a relative path to forward slashes, no leading './'."""
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.strip("/")


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def entries_hash(files):
    """Top-level hash over the sorted entries.

    Canonical form: JSON array of {"bytes","path","sha256"} objects, sorted
    by path, keys sorted, separators (",", ":"), UTF-8. sha256 of that.
    """
    canon = [{"path": e["path"], "bytes": e["bytes"], "sha256": e["sha256"]}
             for e in sorted(files, key=lambda e: e["path"])]
    data = json.dumps(canon, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
    return sha256_bytes(data)


def _is_link_or_junction(entry):
    try:
        if entry.is_symlink():
            return True
    except OSError:
        return True
    isj = getattr(os.path, "isjunction", None)  # Python 3.12+
    if isj is not None:
        try:
            return isj(entry.path)
        except OSError:
            return True
    return False


def walk_tree(root, ignore_abs=()):
    """Walk root without following any symlink or junction.

    Returns (files, skipped). files: list of dicts path/bytes/sha256.
    skipped: list of dicts path/reason. Sensitive names are listed by name
    only and never opened.
    """
    root = os.path.abspath(root)
    ignore = set(os.path.normcase(os.path.abspath(p)) for p in ignore_abs)
    files, skipped = [], []
    stack = [""]
    while stack:
        rel_dir = stack.pop()
        abs_dir = os.path.join(root, rel_dir) if rel_dir else root
        try:
            with os.scandir(abs_dir) as it:
                entries = list(it)
        except OSError as e:
            skipped.append({"path": norm_rel(rel_dir) or ".",
                            "reason": "unreadable directory: %s" %
                            (e.strerror or type(e).__name__)})
            continue
        for entry in entries:
            rel = norm_rel(os.path.join(rel_dir, entry.name))
            if os.path.normcase(os.path.abspath(entry.path)) in ignore:
                continue
            if _is_link_or_junction(entry):
                skipped.append({"path": rel,
                                "reason": "symlink or junction, not followed"})
                continue
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError as e:
                skipped.append({"path": rel, "reason": "cannot stat: %s" %
                                (e.strerror or type(e).__name__)})
                continue
            if stat.S_ISDIR(st.st_mode):
                stack.append(os.path.join(rel_dir, entry.name))
                continue
            if is_sensitive(entry.name):
                skipped.append({"path": rel,
                                "reason": "sensitive name, not opened"})
                continue
            if not stat.S_ISREG(st.st_mode):
                skipped.append({"path": rel, "reason": "not a regular file"})
                continue
            try:
                digest = sha256_file(entry.path)
            except OSError as e:
                skipped.append({"path": rel, "reason": "unreadable: %s" %
                                (e.strerror or type(e).__name__)})
                continue
            files.append({"path": rel, "bytes": st.st_size, "sha256": digest})
    files.sort(key=lambda e: e["path"])
    skipped.sort(key=lambda e: e["path"])
    return files, skipped


def write_with_sidecar(obj, out_path):
    data = (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8")
    with open(out_path, "wb") as f:
        f.write(data)
    digest = sha256_bytes(data)
    side = out_path + ".sha256"
    with open(side, "wb") as f:
        f.write(("%s  %s\n" % (digest, os.path.basename(out_path))).encode(
            "utf-8"))
    return digest, side


def _ignore_paths(out):
    a = os.path.abspath(out)
    return (a, a + ".sha256")


def cmd_manifest(args):
    root = args.dir
    if not os.path.isdir(root):
        print("error: not a directory: %s" % root, file=sys.stderr)
        return 2
    started = utc_now()
    files, skipped = walk_tree(root, _ignore_paths(args.out))
    ended = utc_now()
    obj = {
        "format": MANIFEST_FORMAT,
        "tool": TOOL,
        "header": HEADER,
        "named_point": NAMED_POINT,
        "root": os.path.abspath(root),
        "host": args.host or "",
        "captured_at": {"start_utc": started, "end_utc": ended},
        "path_separator": "/",
        "file_count": len(files),
        "total_bytes": sum(e["bytes"] for e in files),
        "entries_hash_method": "sha256 of JSON array of {path,bytes,sha256} "
                               "sorted by path, sort_keys, separators (',',':'), UTF-8",
        "entries_sha256": entries_hash(files),
        "files": files,
        "excluded": skipped,
    }
    digest, side = write_with_sidecar(obj, args.out)
    print("manifest: %s" % args.out)
    print("files: %d  excluded: %d  entries_sha256: %s" %
          (len(files), len(skipped), obj["entries_sha256"]))
    print("manifest sha256: %s  (sidecar %s)" % (digest, side))
    return 0


def load_base(path):
    """Load any Base manifest with a files[] list of path + sha256 entries.

    Accepts 'bytes' or 'size' for the size. Backslash paths are normalized
    to '/'. Returns (raw_bytes, obj, entries dict path->entry, notes).
    """
    with open(path, "rb") as f:
        raw = f.read()
    obj = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(obj, dict) or not isinstance(obj.get("files"), list):
        raise ValueError("base manifest has no files[] list")
    entries, notes = {}, []
    for i, e in enumerate(obj["files"]):
        if not isinstance(e, dict) or not isinstance(e.get("path"), str):
            raise ValueError("files[%d] has no path" % i)
        p = norm_rel(e["path"])
        size = e.get("bytes", e.get("size"))
        sha = e.get("sha256")
        if isinstance(sha, str):
            sha = sha.lower()
        else:
            sha = None
        if p in entries:
            raise ValueError("duplicate path in base: %s" % p)
        entries[p] = {"path": p, "bytes": size, "sha256": sha}
    stated = obj.get("entries_sha256")
    if stated is not None:
        full = [v for v in entries.values()
                if v["sha256"] is not None and v["bytes"] is not None]
        if len(full) == len(entries):
            calc = entries_hash(full)
            if calc != stated:
                raise ValueError("base entries_sha256 mismatch: stated %s, "
                                 "computed %s" % (stated, calc))
            notes.append("base entries_sha256 verified")
        else:
            notes.append("base entries_sha256 not verified: some entries "
                         "lack sha256 or size")
    else:
        notes.append("base has no entries_sha256 field; file list used as is")
    return raw, obj, entries, notes


def cmd_check(args):
    if not os.path.isdir(args.dir):
        print("error: not a directory: %s" % args.dir, file=sys.stderr)
        return 2
    try:
        raw, base_obj, base, notes = load_base(args.base)
    except (OSError, ValueError) as e:
        print("error: cannot load base manifest: %s" % e, file=sys.stderr)
        return 2
    base_sha = sha256_bytes(raw)
    files, skipped = walk_tree(args.dir, _ignore_paths(args.out))
    box = {e["path"]: e for e in files}
    skipped_by_path = {s["path"]: s["reason"] for s in skipped}

    match, changed, missing, extra, unverified = [], [], [], [], []
    for p in sorted(base):
        b = base[p]
        if p in box:
            x = box[p]
            if b["sha256"] is None:
                unverified.append({"path": p, "reason":
                                   "base entry has no sha256"})
            elif x["sha256"] == b["sha256"] and (
                    b["bytes"] is None or x["bytes"] == b["bytes"]):
                match.append({"path": p, "bytes": x["bytes"],
                              "sha256": x["sha256"]})
            else:
                changed.append({"path": p,
                                "base_bytes": b["bytes"],
                                "base_sha256": b["sha256"],
                                "box_bytes": x["bytes"],
                                "box_sha256": x["sha256"]})
        elif p in skipped_by_path:
            unverified.append({"path": p, "reason": skipped_by_path[p]})
        else:
            missing.append({"path": p, "base_bytes": b["bytes"],
                            "base_sha256": b["sha256"]})
    for p in sorted(box):
        if p not in base:
            extra.append({"path": p, "bytes": box[p]["bytes"],
                          "sha256": box[p]["sha256"]})
    skipped_not_in_base = [s for s in skipped if s["path"] not in base]

    conforms = not changed and not missing and not unverified
    verdict = "CONFORMS" if conforms else "DOES_NOT_CONFORM"
    receipt = {
        "header": HEADER,
        "format": RECEIPT_FORMAT,
        "tool": TOOL,
        "box": args.box,
        "checked_at_utc": utc_now(),
        "named_point": NAMED_POINT,
        "base_manifest": {
            "path": os.path.abspath(args.base),
            "sha256": base_sha,
            "format": base_obj.get("format"),
            "entries_sha256": base_obj.get("entries_sha256"),
            "notes": notes,
        },
        "box_root": os.path.abspath(args.dir),
        "box_entries_sha256": entries_hash(files),
        "verdict": verdict,
        "verdict_rule": "CONFORMS only if CHANGED, MISSING, and UNVERIFIED "
                        "are all empty; EXTRA is reported and allowed",
        "counts": {
            "base_files": len(base),
            "MATCH": len(match),
            "CHANGED": len(changed),
            "MISSING": len(missing),
            "EXTRA": len(extra),
            "UNVERIFIED": len(unverified),
            "SKIPPED": len(skipped_not_in_base),
        },
        "MATCH": match,
        "CHANGED": changed,
        "MISSING": missing,
        "EXTRA": extra,
        "UNVERIFIED": unverified,
        "SKIPPED": skipped_not_in_base,
        "receipt_sha256": "in sidecar file <receipt>.sha256",
    }
    digest, side = write_with_sidecar(receipt, args.out)
    c = receipt["counts"]
    print("box: %s  verdict: %s" % (args.box, verdict))
    print("MATCH %d  CHANGED %d  MISSING %d  EXTRA %d  UNVERIFIED %d  "
          "SKIPPED %d" % (c["MATCH"], c["CHANGED"], c["MISSING"], c["EXTRA"],
                          c["UNVERIFIED"], c["SKIPPED"]))
    print("base manifest sha256: %s" % base_sha)
    print("receipt: %s  sha256: %s  (sidecar %s)" % (args.out, digest, side))
    return 0 if conforms else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="conformance.py",
                                 description="Agape Conformance checker v0")
    sub = ap.add_subparsers(dest="cmd")
    m = sub.add_parser("manifest", help="write a Base manifest for a dir")
    m.add_argument("dir")
    m.add_argument("--out", required=True)
    m.add_argument("--host", default="", help="optional host name to record")
    c = sub.add_parser("check", help="check a box's dir against a Base")
    c.add_argument("base")
    c.add_argument("dir")
    c.add_argument("--box", required=True, help="box designation, e.g. BOX-A")
    c.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "manifest":
        return cmd_manifest(args)
    if args.cmd == "check":
        return cmd_check(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
