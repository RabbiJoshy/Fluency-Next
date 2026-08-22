# Decision 0010: legacy French Speech import candidate

## Status

Gate 10a implemented. Candidate activation is deliberately withheld.

## Migration boundary

The currently shipped legacy French Speech index contains 12,000 rows. The old
app removes 315 `POS=X` meanings with blank translations, leaving 11,685
teachable rows. Surface identity merges those into 9,863 cards while retaining
each source lemma and six-character legacy ID as provenance only.

The importer preserves the first surviving legacy position as rank. It does not
rerank by summed frequency: that would move 9,821 of the initially audited
9,920 raw surfaces because large frequency ties dominate the tail. Each card
retains its primary and aggregate legacy counts for inspection.

Exact duplicate meanings within a surface are coalesced and retain every source
record. Examples remain attached to their exact merged sense. The resulting
candidate contains 13,764 senses and 51,074 examples; 1,575 cards truthfully
carry an empty example list. No example, grammar label, confidence, or WSD run
is invented.

## Provenance and run isolation

The source index and examples are stored once under `objects/sha256/`. The
deterministic import run lives under:

```text
runs/fr/speech/20260426T195234Z-4993b09e/
  manifest.json
  stages/{legacy_import,surface_merge,release_build}.json
  diagnostics/{summary.json,rejections.jsonl}
```

The 315 excluded rows are retained in `rejections.jsonl`. Composition selects
the exact source artifact for inventory, sense menu, sentences, frozen legacy
assignment, and example selection. No fallback is enabled and no other release
is scanned or blended.

## Study structure

The existing adaptive approximately-200-card level algorithm now runs at build
time. Its output is release metadata: 50 levels and 506 stable sets of at most
20 ordered surface positions. Filters and future assignment runs cannot move a
card between sets at runtime.

## Candidate and deferred format decision

`fr-speech-legacy-0001` is catalogued but not active. It is a full-fidelity
33.0 MB single-file benchmark. A browser check loaded correctly and exposed all
import metadata, but the monolith is not an efficient activation target.

Measured alternative: a compact card directory is approximately 2.47 MB, and
50 full-card level shards total the same content while each request is only
383–950 KB (median 654 KB). Implementing that layout must use a new immutable
release ID and requires explicit approval; `0001` remains available for exact
comparison.
