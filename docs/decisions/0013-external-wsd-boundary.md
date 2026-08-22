# Decision 0013: external WSD assignment boundary

**Status: accepted and implemented on 2026-08-22.**

## Scope

WSD method research is happening separately from the repository migration. The
migration therefore owns the immutable interface around WSD, not the choice,
evaluation, or execution of a French method.

An external method may use embeddings, rerankers, alignment, morphology,
clitic promotion, or later machinery without changing the run layout. It hands
back one `wsd-assignment-bundle/v1` JSON file under the workspace's `raw/wsd/`
directory. The canonical schema is
`schemas/wsd-assignment-bundle.schema.json`.

## Required guarantees

- The bundle identifies exactly one run, language, and mode.
- It pins the exact inventory, sense-menu, harvested-candidate, and sentence-bank
  content hashes it consumed.
- It records the external implementation version and content ID, all model
  revisions, and its random seed.
- It contains exactly one explicit result for every retained card/sentence
  candidate. `assigned`, `rejected`, `abstained`, and `no_menu` are records;
  omission is never treated as a decision.
- Assigned results bind to an analysis and leaf that actually exist in the
  run-owned menu. Their headword/POS tuple must match that analysis.
- Import refuses stale inputs, partial coverage, extra candidates, duplicate
  candidates, mismatched surfaces, implicit fallback, and overwrite.

## Publication

The importer republishes validated results once at:

```text
runs/<language>/speech/<run-id>/stages/04_wsd_assignments/output/
├── assignments.jsonl
├── method.json
├── report.json
└── manifest.json
```

The original handoff bundle remains a pinned raw input. Stage 04 does not run
models, compare methods, select thresholds, or activate a release. Downstream
example selection reads only the normalized immutable Stage 04 output, so an
old assignment file cannot silently mix with a new run.
