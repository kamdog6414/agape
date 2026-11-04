"""Agape ORDER + RECEIPT loop: shared helpers. Python stdlib only."""
import hashlib, json, os, sys, time

ORDER_SCHEMA = "agape.order.v1"
RECEIPT_SCHEMA = "agape.receipt.v1"
VERDICT_SCHEMA = "agape.verdict.v1"
GENESIS = "GENESIS"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def obj_sha(obj, drop=()):
    return sha_bytes(canon({k: v for k, v in obj.items() if k not in drop}))


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(canon(obj))
    os.replace(tmp, path)


def chain_tail(path):
    """Return the 'sha' of the last line of a jsonl chain, or GENESIS."""
    if not os.path.exists(path):
        return GENESIS
    last = None
    with open(path, "r", encoding="ascii") as f:
        for line in f:
            if line.strip():
                last = line
    return json.loads(last)["sha"] if last else GENESIS


def chain_append(path, body):
    """Append {'prev','sha','body'} where sha = sha256(canon({'prev','body'}))."""
    prev = chain_tail(path)
    line = {"prev": prev, "body": body}
    line["sha"] = sha_bytes(canon(line))
    with open(path, "a", encoding="ascii", newline="\n") as f:
        f.write(canon(line).decode("ascii") + "\n")
    return line["sha"]


def chain_check(path):
    """Return (ok, n, reason)."""
    prev, n = GENESIS, 0
    if not os.path.exists(path):
        return True, 0, "EMPTY"
    with open(path, "r", encoding="ascii") as f:
        for line in f:
            if not line.strip():
                continue
            n += 1
            row = json.loads(line)
            if row.get("prev") != prev:
                return False, n, "BROKEN_PREV"
            if sha_bytes(canon({"prev": row["prev"], "body": row["body"]})) != row.get("sha"):
                return False, n, "BAD_SHA"
            prev = row["sha"]
    return True, n, "OK"


ORDER_FIELDS = ("schema", "id", "issued_by", "issued_at", "target", "goal", "inputs", "run",
                "limits", "pass_test", "report", "idempotency_key", "parent_hash")


def check_order(o):
    for k in ORDER_FIELDS:
        if k not in o:
            return "MISSING_" + k.upper()
    if o["schema"] != ORDER_SCHEMA:
        return "BAD_SCHEMA"
    if not isinstance(o["run"], list) or not isinstance(o["pass_test"].get("argv"), list):
        return "BAD_ARGV"
    for i in o["inputs"]:
        p = i.get("path", "")
        if not p or p.startswith(("/", "\\")) or ".." in p.replace("\\", "/").split("/") or ":" in p:
            return "BAD_INPUT_PATH"
    return "OK"


def safe_rel(p):
    p = p.replace("\\", "/")
    return p and not p.startswith("/") and ".." not in p.split("/") and ":" not in p


def py_cmd():
    exe = sys.executable
    # pythonw.exe cannot hand stdout to children reliably; use python.exe with CREATE_NO_WINDOW.
    if os.name == "nt" and exe.lower().endswith("pythonw.exe"):
        cand = exe[:-len("pythonw.exe")] + "python.exe"
        if os.path.exists(cand):
            exe = cand
    return exe


def expand(argv):
    return [py_cmd() if a == "{py}" else a for a in argv]


def run_argv(argv, cwd, timeout_s, max_rss_mb=None, out_path=None):
    """Run headless. Returns (exit_code, stdout_bytes, note)."""
    import subprocess
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= 1  # STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kw["startupinfo"] = si
    elif max_rss_mb:
        def lim():
            import resource
            b = int(max_rss_mb) * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (b * 4, b * 4))  # address space ceiling (4x rss budget)
            try:
                resource.setrlimit(resource.RLIMIT_DATA, (b, b))
            except Exception:
                pass
        kw["preexec_fn"] = lim
    try:
        p = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout_s, **kw)
        return p.returncode, p.stdout or b"", "OK"
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or b""), "TIMEOUT"
    except OSError as e:
        return 127, str(e).encode(), "EXEC_ERROR"


def walk_files(root):
    out = []
    for d, _, files in os.walk(root):
        for n in files:
            full = os.path.join(d, n)
            out.append(os.path.relpath(full, root).replace("\\", "/"))
    return sorted(out)
