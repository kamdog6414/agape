"""GPT Codex - MOD-SEAT

Round 0 hello-bw: deterministic black-and-white text, without external input.
"""

import json
import sys


def run(request):
    """Accept one typed request and return fixed plain-text output."""
    if type(request) is not dict or set(request) != {"schema"}:
        raise ValueError("request fields")
    if request["schema"] != "agape.hello.request.v0":
        raise ValueError("request schema")
    return {
        "header": "GPT Codex - MOD-SEAT", "schema": "agape.hello.result.v0",
        "status": "delivered", "text": "hello-bw\nAGAPE Round 0\n",
    }


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_):
    raise ValueError("non-finite JSON number")


def main():
    try:
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096:
            raise ValueError("stdin byte limit")
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        result = run(request)
    except (ValueError, UnicodeError, RecursionError) as exc:
        print(json.dumps({"header": "GPT Codex - MOD-SEAT", "status": "failed", "error": str(exc)}, ensure_ascii=True, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
