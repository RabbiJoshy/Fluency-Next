# Build status

## Completed

- Gate 1: created separate local code and generated-workspace roots.
- Gate 2: created the local Python bootstrap, smoke app, tests, and decision log.
- Gate 3: defined deterministic surface-card IDs, the card schema, and French
  surface identity normalization.
- Gate 4: defined and initialized the external workspace, content-addressed
  artifacts, and run/stage manifest contracts.
- Gate 5: defined French tokenization, elision and hyphen routing, contractions,
  lookup candidates, and retained rejection evidence.
- Gate 6: built the deterministic 25-card French Speech fixture release,
  compact release contracts, read-only local release mount, product-parity
  Fluency setup/study experience, isolated progress, explicit candidate
  selection, diagnostics, and browser speech integration.
- Gate 7: restored the original Fluency HTML/CSS product shell, preserved the
  first pilot UI as a tagged and readable reference, added immutable release
  compositions, exact layer provenance and dependency locks, a candidate
  catalog, separate validation/activation, browser hash checks, and an in-app
  release/layer audit.
- Gate 8 (active-study slice): restored the compact study-options surface,
  French/English card direction, automatic speech control, progress summary,
  and an example-first Card Data inspector that exposes every recorded example
  and assigned-sense field plus exact layer provenance. Published immutable
  multi-example candidate `fr-speech-pilot-0003`; `0002` remains selectable.
- Gate 9 (study lifecycle migration): restored release-owned levels and stable
  sets, unseen-only Learn queues, level-wide Review queues, unfinished-session
  resume, and the existing completion, automatic continuation, main-menu and
  redo actions. Session snapshots freeze the exact release and card order so a
  later activation cannot silently replace or dilute an in-progress run.
  Published `fr-speech-pilot-0004`; `0003` and `0002` remain independently
  selectable through an explicit legacy single-set compatibility adapter.
- Gate 10a (full French import candidate): added a strict adapter for the old
  split index/examples format, preserved its exact inputs as hashed artifacts,
  removed the same 315 blank-translation placeholders the old app removed,
  and merged 11,685 teachable lemma rows into 9,863 surface cards. Candidate
  `fr-speech-legacy-0001` contains 13,764 senses, 51,074 examples, 50 immutable
  levels and 506 immutable sets; pilot `0004` remains active. The 33 MB
  full-fidelity candidate is retained as a benchmark and is not approved for
  activation pending a separately reviewed level-sharding format.

## Not started

- Source ingestion and evidence registries.
- Embeddings, WSD, calibration, and example selection.
- Production release generation and full French inventory integration.
- Spanish and legacy progress migration.
- Artist mode.

No production system or existing Fluency repository has been modified. The
pilot uses curated fixture content and makes no production coverage or WSD
claims.
