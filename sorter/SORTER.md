Grok 4.7 - SORTER-SEAT

# Sorter

Named point: NP-20261026T170000Z
Part: Sorter
Owner: Grok 4.7 - SORTER-SEAT
Base: agape.base.v0

Sorter reads the enabled ids and returns the list for `core.set_order(ids)`.
A clear list is the same ids, each once. `set_order` refuses anything else, so a conflict returns no list and does not call `set_order`.

`plan` and `apply` take caller-supplied pairs:

- `before`: pairs `(earlier, later)`. Earlier loads before later.
- `conflicts`: pairs that cannot both be enabled.

`order_round(core, submissions, round_id)` reads one round. Each submission is a dict with `mod_id`, `requires`, and `conflicts`, the shape `verify_package` returns. Sorter does not verify the package and does not import its payload.

- `requires`: that id loads before the submission.
- `conflicts`: that id and the submission cannot both be enabled. A conflict id that is not enabled is not a block.
- A submission that is not enabled is a conflict (`not_enabled`). Manager enables first.

Tie break is the current enabled order. A cycle, a duplicate, an unknown id, a bad declaration, or a conflict pair is a conflict.

No network. No service control. No credential files. No color.
