"""Grok 4.7 - BASE-SEAT. Base interface checks. No network."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base

passed = 0
total = 8
core = base.open_base("BOX-A")
one = core.enable("demo", "a" * 64)
two = core.enable("demo", "b" * 64)
three = core.enable("other", "c" * 64)
mid = core.list_order()
order = core.set_order(["other", "demo"])
ordered = core.list_order()
bad = core.set_order(["demo", "missing"])
off = core.disable("other")
laws = core.note_laws(["private-net-only"])
body = core.probe()
checks = [
    one["result"] == "enabled",
    two["result"] == "refused",
    three["result"] == "enabled" and mid == ["demo", "other"] and ordered == ["other", "demo"],
    order["result"] == "enabled" and bad["result"] == "refused",
    off["result"] == "disabled" and core.list_order() == ["demo"],
    laws["result"] == "enabled" and body["named_point"] == base.NAMED_POINT and body["version"] == "agape.base.v1",
]
point = "e605b853d6eea415073da043a65d9f28fb8b715e669d4ece94b0c74bee88e7b7"
opened = core.open_round("R0", point)
submitted = core.submit("hello-bw", "d" * 64)
scored = core.score("hello-bw", "no-network", "PASS", "e" * 64)
again = core.open_round("R1", point)
state = core.round_state()
checks.append(opened["result"] == "enabled" and submitted["result"] == "enabled" and scored["result"] == "PASS")
checks.append(
    again["result"] == "refused"
    and state["round_id"] == "R0"
    and state["named_point"] == base.NAMED_POINT
    and state["submissions"][0]["mod_id"] == "hello-bw"
    and state["scores"][0]["result"] == "PASS"
)
for i, ok in enumerate(checks, 1):
    print(("PASS" if ok else "FAIL") + " T" + str(i))
    passed += int(ok)
line = ("PASS " if passed == total else "FAIL ") + str(passed) + "/" + str(total)
print(line)
json.dumps(body)
sys.exit(0 if passed == total else 1)
