"""Grok 4.7 - SORTER-SEAT

Sorter for agape.base.v0. Load order and conflict check.
The list it returns is the argument for core.set_order(ids).
Round submissions carry requires and conflicts from agape.mod.v0.
This module does not read package bytes and does not import a payload.
"""

from __future__ import annotations

from collections import defaultdict, deque

NAMED_POINT = "NP-20261026T170000Z"


def plan(
    enabled: list[str],
    before: list[tuple[str, str]] | None = None,
    conflicts: list[tuple[str, str]] | None = None,
) -> dict:
    """Return a set_order list, or the conflicts that block one.

    `before` pairs are (earlier, later). `conflicts` pairs cannot both be enabled.
    A clear plan keeps the incoming order wherever the constraints allow it.
    """
    found: list[dict] = []
    seen: set[str] = set()
    for mod_id in enabled:
        if not mod_id or mod_id in seen:
            found.append({"kind": "duplicate", "id": mod_id})
        seen.add(mod_id)
    enabled_set = set(enabled)

    edges: list[tuple[str, str]] = []
    for earlier, later in before or []:
        if earlier not in enabled_set:
            found.append({"kind": "unknown", "id": earlier})
            continue
        if later not in enabled_set:
            found.append({"kind": "unknown", "id": later})
            continue
        if earlier == later:
            found.append({"kind": "cycle", "ids": [earlier]})
            continue
        edges.append((earlier, later))

    blocked: set[tuple[str, str]] = set()
    for left, right in conflicts or []:
        pair = tuple(sorted((left, right)))
        if pair in blocked:
            continue
        blocked.add(pair)
        if left == right or (left in enabled_set and right in enabled_set):
            found.append({"kind": "pair", "ids": [pair[0], pair[1]]})

    if found:
        return {"ids": None, "conflicts": found, "result": "conflict"}

    indegree = {mod_id: 0 for mod_id in enabled}
    after: dict[str, list[str]] = defaultdict(list)
    for earlier, later in edges:
        after[earlier].append(later)
        indegree[later] += 1

    ready = deque(mod_id for mod_id in enabled if indegree[mod_id] == 0)
    ordered: list[str] = []
    while ready:
        current = ready.popleft()
        ordered.append(current)
        for nxt in after[current]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    if len(ordered) != len(enabled):
        stuck = [mod_id for mod_id in enabled if mod_id not in ordered]
        return {
            "ids": None,
            "conflicts": [{"kind": "cycle", "ids": stuck}],
            "result": "conflict",
        }
    return {"ids": ordered, "conflicts": [], "result": "clear"}


def apply(core, before=None, conflicts=None) -> dict:
    """Plan from core.list_order(). Call set_order only when the plan is clear."""
    current = core.list_order()
    result = plan(current, before, conflicts)
    if result["result"] != "clear":
        result["applied"] = False
        result["receipt"] = None
        return result
    receipt = core.set_order(result["ids"])
    result["applied"] = receipt.get("result") == "enabled"
    result["receipt"] = receipt
    return result


def _submission_rows(submissions) -> tuple[list[dict], list[dict]]:
    """Return usable rows and declaration conflicts. Does not mutate the input."""
    if not isinstance(submissions, list):
        return [], [{"kind": "declaration", "id": ""}]
    rows: list[dict] = []
    problems: list[dict] = []
    seen: set[str] = set()
    for row in submissions:
        if not isinstance(row, dict):
            problems.append({"kind": "declaration", "id": ""})
            continue
        mod_id = row.get("mod_id")
        requires = row.get("requires", [])
        declared = row.get("conflicts", [])
        if not isinstance(mod_id, str) or not mod_id:
            problems.append({"kind": "declaration", "id": ""})
            continue
        if mod_id in seen:
            problems.append({"kind": "duplicate", "id": mod_id})
        seen.add(mod_id)
        if not isinstance(requires, list) or not isinstance(declared, list):
            problems.append({"kind": "declaration", "id": mod_id})
            continue
        if any(not isinstance(item, str) or not item for item in requires):
            problems.append({"kind": "declaration", "id": mod_id})
            continue
        if any(not isinstance(item, str) or not item for item in declared):
            problems.append({"kind": "declaration", "id": mod_id})
            continue
        rows.append(
            {
                "mod_id": mod_id,
                "requires": list(requires),
                "conflicts": list(declared),
            }
        )
    return rows, problems


def order_round(core, submissions, round_id="0") -> dict:
    """Order one round's submissions and feed a clear list to set_order.

    `requires` loads earlier than the submission. `conflicts` cannot both be
    enabled. The enabled set is core.list_order(). A submission that is not
    enabled is a conflict, and set_order is not called.
    """
    enabled = list(core.list_order())
    enabled_set = set(enabled)
    rows, problems = _submission_rows(submissions)
    before: list[tuple[str, str]] = []
    pairs: list[tuple[str, str]] = []
    for row in rows:
        if row["mod_id"] not in enabled_set:
            problems.append({"kind": "not_enabled", "id": row["mod_id"]})
        for required in row["requires"]:
            before.append((required, row["mod_id"]))
        for other in row["conflicts"]:
            pairs.append((row["mod_id"], other))
    planned = plan(enabled, before, pairs)
    conflicts = problems + list(planned["conflicts"])
    result = {
        "round_id": str(round_id),
        "named_point": NAMED_POINT,
        "submissions": [row["mod_id"] for row in rows],
        "ids": None,
        "conflicts": conflicts,
        "result": "conflict" if conflicts else "clear",
        "applied": False,
        "receipt": None,
    }
    if conflicts:
        return result
    receipt = core.set_order(planned["ids"])
    result["ids"] = planned["ids"] if receipt.get("result") == "enabled" else None
    result["applied"] = receipt.get("result") == "enabled"
    result["receipt"] = receipt
    if not result["applied"]:
        result["result"] = "conflict"
        result["conflicts"] = [{"kind": "refused", "ids": list(planned["ids"] or [])}]
    return result
