# Decision 0018 — Offline SpanishDict menu source

## Decision

Rebuild Spanish sense menus from the latest verified SpanishDict caches and
their morphology lookup inputs. Do not migrate the old 42 MB normalized menu,
run the web scraper, or copy any WSD assignments.

The retained snapshot contains only:

```text
surface_cache.json
headword_cache.json
spanish_forms.json
conjugation_reverse.json
```

Every file is hash-pinned under
`raw/dictionaries/es/spanishdict/spanishdict-recovered-2026-08-22-v1/`.
The run-owned adapter validates all four before use and has no HTTP dependency.

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

## Verified 200-card result

Run `20260822T214657Z-db4c1b65` produced 474 normalized headword/POS analyses
and 2,352 leaves for 199 cards. `sr` is the sole `no_menu` surface. Seven plural
analysis collisions were quarantined, 146 leaves explicitly lack a translation,
and there are no fallbacks.

An independent comparison against the latest old-repository builder found zero
missing or extra tuples across surface, headword, POS, legacy sense ID,
translation and context. The same run retained 11,878 sentence candidates for
all 200 surfaces. It did not run WSD, select final examples, build a deck, create
a release or change an active pointer.
