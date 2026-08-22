# Decision 0010: fresh French Speech audit skeleton

## Decision

The first non-fixture French Speech run will be generated from fresh source
snapshots. Historical French cards, meanings, examples, ranks, assignments,
identifiers, and compatibility adapters are not inputs or fallbacks.

The audit scope is exactly 200 surface-form cards and three selected examples
per card (600 examples total). A shortfall blocks release construction instead
of borrowing an example from an older run. Release activation is always a
separate manual action.

## Stage boundary

Each run exposes one folder per decision layer:

1. `01_inventory`: fresh ranked surface inventory; no lemma card identity.
2. `02_sense_menu`: fresh senses and translations for the exact inventory.
3. `03_sentence_harvest`: fresh bilingual examples with source evidence.
4. `04_wsd_assignments`: embeddings plus a language-specific reranker, with
   exact model revisions required before execution.
5. `05_example_selection`: exactly three assigned examples per surface.
6. `06_release_build`: compose an inactive, immutable app candidate from the
   exact approved artifact hashes.

Planning creates only the manifest, frozen profile, plan, and pending contracts.
It does not install ML libraries, download corpora or models, execute stages, or
publish a release. Expensive commands will be supplied for local execution once
their source and model decisions have been approved.

## Dependency policy

The orchestration core remains Python-standard-library-only. Source clients and
model runtimes will be isolated behind stage adapters and installed as explicit
optional dependencies only when a chosen implementation requires them. A stage
records its implementation hash, configuration hash, input artifact hashes,
model revisions, and output artifact hashes so a rerun cannot silently consume
another run's data.
