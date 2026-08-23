# Decision 0018 — Offline SpanishDict menu source

## Decision

Pin the complete deterministic SpanishDict menu alongside the verified raw
caches and morphology lookup inputs. Do not run the web scraper or copy any WSD
assignments.

The original 2026-08-22 decision excluded the old 42 MB normalized menu after a
200-card parity check. That check did not establish full-inventory coverage:
the raw surface cache reconstructed 199/200 menus but only 1,520/2,000. The
retained normalized menu covers 1,988/2,000 and is dictionary evidence, not a
WSD assignment. It is therefore a required pinned input. Spanish profiles also
set an explicit 99% minimum card-coverage gate so this failure cannot silently
recur.

The retained snapshot contains only:

```text
surface_cache.json
headword_cache.json
spanish_forms.json
conjugation_reverse.json
normalized_menu.json
```

Every file is hash-pinned under
`raw/dictionaries/es/spanishdict/spanishdict-complete-menu-2026-08-23-v1/`.
The run-owned adapter validates every retained file before use and has no HTTP
dependency.

## Provider-specific behavior behind a shared contract

- Cards remain surface-identified. SpanishDict headwords are lookup metadata.
- Direct responses, conjugation/inflection candidates and response language
  remain explicit provider evidence.
- Phrase-only self analyses are removed when a real conjugation analysis exists.
- Simple plural twins, abbreviation mismatches, reverse-direction responses and
  implausible fuzzy headwords follow the latest Spanish pipeline safeguards.
- Rejected analyses are quarantined with a reason; missing menus remain
  explicit and never trigger a dictionary fallback.
- Existing short SpanishDict menu IDs are preserved within each surface menu so
  progress and future imported assignments can be reconciled.
- A missing provider translation is valid only as an explicit empty value with
  `translation_status: explicit_missing`; its context and metadata survive.

## Verified results

Run `20260822T214657Z-db4c1b65` produced 474 normalized headword/POS analyses
and 2,352 leaves for 199 cards. `sr` is the sole `no_menu` surface. Seven plural
analysis collisions were quarantined, 146 leaves explicitly lack a translation,
and there are no fallbacks.

An independent comparison against the latest old-repository builder found zero
missing or extra tuples across surface, headword, POS, legacy sense ID,
translation and context. The same run retained 11,878 sentence candidates for
all 200 surfaces. It did not run WSD, select final examples, build a deck, create
a release or change an active pointer.

Corrected run `20260823T215525Z-5836dcc4` produced 4,300 analyses and
23,746 leaves for 1,988 of 2,000 cards. The 12 unresolved surfaces are primarily
abbreviations/noise. The previous partial-input run produced only 1,520 menus
and is not suitable as a learner release.
