# Decision 0016 — Retained Spanish migration sources

## Decision

The first clean Spanish deck reuses the audited harvested sentence bank,
candidate mapping and paid Gemini exact-text embeddings. It does not reharvest
or recount the 61-million-line OpenSubtitles corpus merely to prove migration.

The current 9,999-surface inventory is also retained as a reconstructed ranking
source so the migrated deck preserves familiar ordering. New run outputs are
still built from scratch: no WSD assignment, final three-example selection,
compact deck, release or active pointer is imported.

## Pinned workspace assets

```text
raw/inventories/es/recovered/fluency-2026-07-28-surface-ranking-v1/
raw/sentence_banks/es/opensubtitles/2026-08-15-harvest-v1/
raw/embeddings/google-gemini/gemini-embedding-001/recovered-2026-08-20-v1/
```

Each directory has a `retained-source-artifact/v1` manifest containing exact
file hashes, byte and record counts, the audited source commit, recovery time,
coverage and known provenance gaps. Unknown source URI/license values remain
unknown. The old Gemini inner manifest's stale 17,861 count is retained as
historical evidence but overridden by the mutually consistent 276,724-row
exact-text index and vector matrix.

## Identity and contamination boundary

- The recovered source may contain `known_lemmas`, but the inventory adapter
  emits only surface card IDs, surface/display form and sequential rank.
- The profile must explicitly set `allow_recovered_inputs: true`; fresh French
  profiles set it to false. Recovered permission and adapter selection must
  agree or planning fails.
- The sentence bank's `clean` and `held` pools are evidence, not final picks.
- Gemini cache keys are exact text; changed menu or sentence text is a miss.
- Assignment, selection and release paths are not among the migration inputs.

## Verified result

- 9,999 unique ranked surfaces pinned.
- 42,650 sentence records and 51,193 candidate links pinned.
- 276,724 Gemini vectors at 3,072 float16 dimensions pinned.
- Fresh 20-card and 200-card inventories built with unique surface IDs and no
  lemma fields.
- Every one of the first 200 surfaces has retained sentence evidence; the
  minimum is six candidate sentences.
- No Spanish release was created or activated.
