Muse Wonder - LAWS-SEAT
# AGAPE LAWS v1 - PREDICATES

PART: LAWS
Named point: NP-20261026T170000Z
Status: v1, built against agape.base.v0 (INTERFACE.md sha256 a40e530a26d92b749c7f79c54eb1b4cd7bce04f7942e9a303733a1e402e6b9b0).
Code: laws.py in this directory. Tests: test_laws.py.

Base does not evaluate laws. This module evaluates them and hands the
names that passed to core.note_laws(names). Names carry no spaces,
as note_laws requires.

## The four predicates

named_point_hash(manifest_path)
  Law: L-11, the point. The box's named-point manifest copy must hash
  to the pin e605b853d6eea415073da043a65d9f28fb8b715e669d4ece94b0c74bee88e7b7.
  Method: sha256 of the file's bytes, compared to the pin.
  A missing or unreadable file fails. This is the predicate the LAWS
  assignment itself was gated on; LAWS-SEAT confirmed it at 2026-10-26
  10:23 PDT before building.

no_secrets_in_mod(mod_root)
  Law: L-14, containment. A mod ships no secret material.
  Method: every file in the mod is checked twice. The file name is
  matched against secret-bearing names (secret, token, credential,
  password, .pem, .key, .env). Text content is matched against
  private-key headers, AWS key ids, GitHub token shapes, sk- keys,
  and key/token/password assignments with quoted values.
  Hits are reported as paths, never values.

no_network(mod_root)
  Law: L-14, containment. Agape stays on the private network; a mod adds no
  network capability of its own.
  Method: static scan of text files for network imports (socket,
  urllib, requests, http.client, http.server, websocket, ftplib,
  smtplib, telnetlib, aiohttp, httpx), socket construction and
  connection calls, the wide bind 0.0.0.0, and the word funnel.

black_and_white(mod_root)
  Law: L-16, surface. Visuals are black and white only.
  Method: scan of every readable text file for machine-readable
  color encodings: ANSI escape sequences, CSS color properties
  (color, background, background-color, border-color), and
  rgb/rgba/hsl/hsla functions.

## Scope, stated plainly

These are static, pattern-based checks. A pass means: these checks
found no evidence against the law. It is not a proof that no secret,
no network path, and no color exists by some other encoding. The
checks are versioned with the laws; a v2 widens the patterns, it
does not quietly change what a v1 pass meant.

Composition proof: test_laws.py builds a clean mod and a dirty mod,
evaluates both, then calls the real Base on this box -
open_base("BOX-C"), note_laws(passed names), probe() - and prints
the probe. A clean mod passes all four names into Base.

Muse Wonder - LAWS-SEAT
