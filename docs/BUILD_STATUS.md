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
  Published `fr-speech-pilot-0004` as the first supported study-structure format.
- Gate 10 (fresh-run skeleton): removed the historical split-deck importer,
  legacy provenance fields, and old study-structure compatibility path. Added
  an auditable French Speech profile fixed at 200 surface cards and three
  examples each, with separate inventory, sense-menu, sentence-harvest, WSD,
  example-selection, and release-build contracts. Planning executes no data or
  model work and never activates a release.
- Gate 11 (exact app transplant): replaced the compact prototype runtime with
  the current Fluency HTML/CSS/JavaScript application, while retaining the
  prototype HTML as a reference. Added release-generated split-data assets and
  server aliases so the existing app loads only the manually active immutable
  release. The repository contains no copied historical `Data/` or `Artists/`
  tree. Active-release aliases bypass service-worker caches, and the legacy
  Merge Lemmas control is hidden for surface-only releases. Published and
  browser-verified `fr-speech-pilot-0005` through guest entry, French setup,
  20-card Learn start, card flip, meaning, and three-example display.
- Gate 12 (language-agnostic harvesting): added a shared streaming harvester,
  shared Speech rules, French normalization/rule overlays, and explicit
  Tatoeba and aligned-OpenSubtitles adapters. The run reads only its own
  surface inventory, requires raw snapshots inside the external workspace,
  retains up to 60 candidates per surface, preserves source-specific
  provenance in one canonical sentence schema, hashes every input/output, and
  refuses overwrite or source fallback. Synthetic French tests prove 20
  surface cards x 3 candidates for Tatoeba and movie/line provenance for
  OpenSubtitles. No real corpus run or WSD was executed.
- Gate 13 (closed-menu WSD and Wiktionary): captured the current Spanish
  retrieval, tuple-reranking, calibration, alignment, and disposition layers
  behind fail-closed shared contracts, with French-specific model choices
  truthfully benchmark-blocked. Added a pinned English-Wiktionary/Kaikki
  adapter that preserves exact headword/POS analyses, structured form-of
  targets, stable provider leaves, metadata, and explicit no-menu cases.
  French menu policy constrains redirects by source/target POS, rejects
  abbreviation expansion unless it is a contraction, and requires redirect
  source case to match. This prevents dictionary-edge leakage such as
  `de → dame`, conjugated verbs importing noun twins, and `cette → Sète`.
- Gate 14 (fresh French surface inventory): added an immutable Lexique 4.00
  adapter using its subtitle-corpus `FreqOrtho` surface measure. Stage 01 emits
  exactly the profile's surface cards plus full frequency ranks and an audit
  report, while deliberately excluding Lexique lemmas, POS, inflection data,
  legacy French files, fallback, overwrite, and automatic activation. Reviewed
  surface exclusions live in a French policy overlay; `ca` is excluded without
  redirect because its Lexique frequency and Wiktionary meaning conflict, while
  accented `ça` retains its own identity.
- Gate 15 (official Tatoeba snapshot contract): replaced the ManyThings ZIP
  assumption with Tatoeba's official weekly detailed French/English sentence
  exports and direct translation links. A pinned directory manifest preserves
  the exact language pair, upstream headers and URLs, license, contributors,
  sentence IDs and timestamps; all compressed inputs contribute to the stage
  hash. The same adapter is configured for French, Spanish, Dutch and
  Portuguese language codes.
- Gate 16 (real French harvest): run `20260822T172017Z-651bcd8e` scanned
  438,157 official French-English links and retained 11,931 candidate
  assignments across all 200 surface cards. No card has a shortfall: the
  minimum is 23 candidates and 19 distinct French sentence IDs. All 7,671
  retained sentence records have complete source attribution, contributor and
  license fields, and every stage/contract content hash verifies.
- Gate 17 (French WSD gold pack): generated an immutable prediction-blind
  benchmark from the real run with 120 unique cards and sentence pairs: 40
  function/homograph, 40 inflected/multi-headword and 40 ordinary multi-sense.
  A self-contained local review screen saves and resumes by exact benchmark ID,
  supports explicit missing-sense/bad-pair/unsure outcomes, and exports/imports
  exact analysis-and-leaf labels. Browser verification covered selection,
  navigation, reload persistence and reset; the delivered review starts at
  zero labels.

## Not started

- Gold annotation of the frozen 120-row French WSD benchmark.
- Pinned French embedding/reranker models, WSD, calibration, and selection.
- Production release generation and full French inventory integration.
- Spanish and legacy progress migration.
- Release diagnostics and release-frozen resume behind the transplanted app.
- Artist mode.

No production system or existing Fluency repository has been modified. No old
French deck data is an input to the clean pipeline. The active pilot uses
curated fixture content and makes no production coverage or WSD claims.
