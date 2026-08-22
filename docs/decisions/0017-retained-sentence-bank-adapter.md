# Decision 0017 — Retained Spanish sentence-bank adapter

## Decision

Treat the verified migrated Spanish sentence bank as an explicit harvesting
source, not as a raw OpenSubtitles snapshot and not as a completed assignment
layer. The `retained-sentence-bank/v1` adapter validates the retained artifact,
converts every sentence into the shared parallel-sentence contract, and lets
each new run rebuild surface matching, quality metrics and candidate caps.

This removes raw reharvesting from the migration critical path without allowing
old WSD, clean/held labels, final example choices or releases into the new run.

## Provenance and identity

- The adapter verifies `sentence_bank.jsonl`, `word_candidates.json` and
  `harvest_manifest.json` against the immutable artifact manifest before use.
- The old sentence ID remains `source_record_id` evidence. A new canonical
  sentence ID binds the adapter, complete retained snapshot, old ID and exact
  Spanish/English text.
- Movie, subtitle and line metadata remain under `source.document`.
- Historical harvest scores and gates are namespaced under
  `source.provider_data.legacy_quality`; they are not current decisions.
- Unknown URI and license remain explicit unknown values rather than being
  invented during migration.
- The old candidate map is hash-verified source evidence. The shared harvester
  rematches the complete sentence bank and does not accept its clean/held pools
  as final selections.

## Verified runs

| Run | Cards | Retained assignments | Distinct sentences | Minimum per card |
| --- | ---: | ---: | ---: | ---: |
| `20260822T212608Z-702ef1b0` | 20 | 1,200 | 681 | 60 |
| `20260822T212645Z-df19d6d0` | 200 | 11,878 | 6,094 | 10 |

Both runs scanned the 42,650 retained sentence records only. Neither ran WSD,
made final three-example selections, built a deck release or changed an active
release pointer. A future raw OpenSubtitles harvest and corpus-frequency scan
remain optional experiments, not migration prerequisites.
