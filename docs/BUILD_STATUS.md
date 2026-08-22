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
  Published `fr-speech-pilot-0004` as the only supported pilot format.
- Gate 10 (fresh-run skeleton): removed the historical split-deck importer,
  legacy provenance fields, and old study-structure compatibility path. Added
  an auditable French Speech profile fixed at 200 surface cards and three
  examples each, with separate inventory, sense-menu, sentence-harvest, WSD,
  example-selection, and release-build contracts. Planning executes no data or
  model work and never activates a release.

## Not started

- Fresh frequency, dictionary, and sentence-source adapters.
- Execution of the 200-card inventory and 600-sentence harvest.
- Pinned French embedding/reranker models, WSD, calibration, and selection.
- Production release generation and full French inventory integration.
- Spanish and legacy progress migration.
- Artist mode.

No production system or existing Fluency repository has been modified. No old
French deck data is an input to the clean pipeline. The active pilot uses
curated fixture content and makes no production coverage or WSD claims.
