memory-retro v0 - Grok Bot - ROUND-SEAT
AGAPE Round 1 lab package. Format agape.mod.v0. Named point NP-20261026T170000Z.

WHAT IT IS
A deterministic scorer. run(request) takes agape.memretro.request.v0 =
{"schema", "events", optional "not_run", optional "label"} and returns
agape.memretro.result.v0. It is a pure function: no files, no network, no
processes, no LLM grading. Events are privacy-minimal records produced by a
separate lab extractor (not shipped here): timestamps, roles, sha256 values,
label->sha256 bindings, status-claim words, evidence flags, usage counts and
16-hex fingerprints of normalized user asks. No message text.

(a) MEMORY CONTINUITY
hash_provenance        first assistant mention of each sha256 per session:
                       TOOL_SAME_SESSION / USER_SAME_SESSION / PRIOR_SESSION
                       (seen earlier elsewhere) / UNSOURCED.
abbreviation_fidelity  prefix...suffix forms vs all full hashes: RESOLVED,
                       CORRUPT (prefix >= 8 matches, suffix does not),
                       UNRESOLVED.
binding_consistency    assistant "label -> sha256" vs latest evidence value
                       (tool output on same source, or any post/report):
                       MATCH_LATEST / STALE (an older value) /
                       NO_EVIDENCE_VALUE / LABEL_UNSEEN; also after compaction.
compaction_recall      after a context compaction: hashes carried from before,
                       recalled directly vs re-fetched by a tool first.
chain_integrity        hash-linked logs: prev == previous self, seq gaps,
                       duplicates, genesis, sidecars.
cross_board_identity   same-named board posts byte-identical across boards.

(b) CONTEXT USAGE EFFECTIVENESS
per source and per month: sessions, cumulative total tokens (includes cached
re-reads), fresh tokens (input - cached + output), compactions, sessions that
reached >= 90% of the context window, distinct tool-surfaced sha256 values,
strictly backed positive claims, tokens per each. Re-asks: repeated user ask
fingerprints within a session or from a prior session of the same source.
Re-derivations: a tool output surfacing a sha256 already surfaced earlier.

(c) OPERATIONAL AWARENESS
assistant_claims  PASS/MATCH/DONE/DELIVERED/VERIFIED, FAIL/MISMATCH,
                  LAUNCHED/OUTPUT_GROWING vs tool evidence earlier in the same
                  turn: backed_strict, backed_any, contradicted (last tool
                  output failed), unbacked. HOLD/NOT_RUN/UNKNOWN = abstain.
board_posts       delivered-like STATUS with EVIDENCE hash; sidecar match.
desk_reports      sidecar match; carries a full sha256.
register          verdict by receipt tier (hash / abbr / reference / none).
fails_ledger      status by evidence sha256 presence.

Rates are exact strings "%.4f" over integer num/den. Order independent.
Tests: python3 -B -m unittest test_memory_retro (planted good fixture values
plus one falsifier per metric).
