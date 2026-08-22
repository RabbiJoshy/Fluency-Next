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
- Gate 17 (external WSD boundary): added a method-independent, fail-closed
  importer for a complete assignment bundle produced by the separate WSD task.
  It pins the exact run and all four upstream artifact hashes, validates every
  candidate disposition and selected menu leaf, records external method/model
  provenance, publishes immutable Stage 04 output once, and cannot merge with
  or overwrite an older assignment layer. No WSD method was selected, compared,
  or executed.
- Gate 18 (WSD-independent release contract): example selection now depends on
  the run-owned inventory and harvest, not on WSD. Profiles publish up to three
  examples per card with explicit coverage; missing assignments and shortfalls
  remain visible in the release and cannot cause an old-run fallback or block
  the whole deck. The app adapter maps unassigned examples to its existing
  unassigned sense-cycle UI instead of inventing a sense link.
- Gate 19 (real French app candidate): selected 600 examples from the verified
  Tatoeba harvest without WSD and composed the real-data candidate family
  `fr-speech-real-tatoeba-unassigned-0001`–`0003`. It contains 200 surface cards,
  1,180 card-scoped Wiktionary sense options, full per-example source metadata,
  and exactly 600 explicitly unassigned examples.
- Gate 20 (release-owned setup verified): fixed the transplanted app adapter so
  a wholly unassigned deck remains teachable without claiming a sense. Every
  release now publishes its immutable numbered levels and set membership as an
  app asset; active vocabulary, examples and study structure all bypass stale
  service-worker aliases. Locally activated and browser-verified
  `fr-speech-real-tatoeba-unassigned-0003`: French setup shows 10 numbered
  levels, Level 1 shows one 20-card set, Learn opens the real rank-1 card
  `de`, and its three unassigned Tatoeba examples render normally.
- Gate 21 (bounded frontend audit): removed the abandoned Spanish Speech
  preview and unused pipe-delimited CSV loader; added source-specific runtime
  guards for vocabulary and example assets; made configured-file failures
  explicit; strengthened release validation so set/level rank metadata cannot
  disagree with exact card membership; and made Card Data available to guests.
  Larger Lyrics functionality and compatibility for unmigrated languages are
  retained intentionally. Deferred cleanup is recorded without blocking the
  Spanish migration.
- Gate 22 (audit identity and account memory): the transplanted app now reads
  the active immutable release manifest and composition through uncached stable
  aliases, and attaches the exact release, run, content and layer identity to
  audit flags. `JSTA` shares JST's audit tools while retaining its own user
  progress. Custom Lyrics selections retain both exact song IDs and their
  contributing artist slugs. The shared local Apps Script contract remains in
  the existing Fluency repository until backend migration and must be deployed
  manually after changes.
  Flags are append-only events keyed by an immutable `FlagId`: delivery retries
  update only their own event, while a later report on the same card/field
  remains separate. Client-build and source-record IDs are promoted for common
  audits, and resolution state can identify the release that fixed a report.
- Gate 23 (Spanish planning contracts): added non-executing Spanish Speech
  rehearsal (20×3) and audit (200×3) profiles using the shared surface,
  harvesting, menu, WSD and release contracts. Spanish normalization preserves
  accents and complete observed clitic surfaces; SpanishDict headwords remain
  lookup metadata; response mismatches and fuzzy corrections are explicit; and
  aligned OpenSubtitles is the exclusive configured audit source. The audited
  `sd-beto-cal-v5` method, source commit, Gemini/BETO/calibrator identities and
  held-out alignment result are captured in a blocked method profile. No old
  assignment, model asset, inventory, corpus stage or release was executed or
  activated. Its explicit frequency-source gate is resolved by Gate 25.
- Gate 24 (reusable corpus-frequency source): added an optional path for using
  the pinned Spanish side of aligned OpenSubtitles as a future ranking source,
  with a language-agnostic streaming compiler. It hashes raw bytes while counting,
  reports progress every million lines, preserves accents and complete surface
  forms, rejects configured markup/music/URL lines, and publishes a reusable
  immutable ranked snapshot with explicit provenance and unknown license/URI
  fields. Run-owned inventories consume that snapshot quickly, so the 2 GB
  corpus is never rescanned for 20×3 and 200×3 separately. Fixture compilation
  and Spanish inventory selection are tested; the real scan has not run.
- Gate 25 (retained Spanish sources and fresh inventory): changed the migration
  path so a full 61-million-line frequency scan is optional rather than a
  prerequisite. Byte-verified immutable workspace snapshots now retain exactly
  the 9,999-surface source ranking, 42,650 OpenSubtitles sentence records,
  51,193 clean/held candidate links across 9,954 surfaces, and the 276,724-row
  Gemini exact-text cache with its `(276724, 3072)` float16 matrix. No WSD
  assignment, final example choice, deck output or release was copied. Fresh
  runs `20260822T212111Z-03f24222` and `20260822T212159Z-f423f132` produced
  20-card and 200-card surface-only inventories. The 200-card inventory has 200
  unique cards, no lemma fields, and all 200 surfaces have at least six retained
  candidate sentences. No Spanish release was activated.
- Gate 26 (retained sentence-bank adapter): added an explicit
  `retained-sentence-bank/v1` source adapter which validates all three retained
  bank files against their manifest, converts old records into the shared
  parallel-sentence contract, preserves old IDs as source-record evidence, and
  rebuilds matching, quality metrics and candidate caps inside each new run.
  It never treats old clean/held pools as final selections. Spanish runs
  `20260822T212608Z-702ef1b0` and `20260822T212645Z-df19d6d0` scanned only the
  42,650 retained records—not the raw corpus—and retained 1,200 candidates for
  20 cards and 11,878 for 200 cards. The 200-card minimum is ten candidates;
  there are no shortfalls, WSD assignments, final picks or activated release.
- Gate 27 (offline SpanishDict adapter): pinned the latest verified surface and
  headword caches plus Spanish forms and reverse conjugations as four immutable
  offline inputs. The provider adapter preserves surface-card identity and
  legacy leaf IDs, applies the latest conjugation, phrase, plural, language and
  fuzzy-headword safeguards, and records explicit quarantine/no-menu outcomes.
  Run `20260822T214657Z-db4c1b65` exactly matches all 2,352 leaves produced by
  the latest old-repository builder across surface, headword, POS, sense ID,
  translation and context. It has 474 headword/POS analyses for 199 cards,
  seven quarantined plural twins, 146 explicit missing translations, and one
  honest no-menu card (`sr`). No scraper, fallback, WSD, final selection,
  release build or activation ran.
- Gate 28 (unassigned Spanish audit release): generalized the run candidate
  builder so provider, locale, label and progress namespace are not hard-coded
  to French/Wiktionary, and preserved complete menu metadata into the app data.
  Explicitly missing translations are valid only with provider status and a
  usable context. Inactive release `es-speech-audit-200-unassigned-20260822`
  validates with 200 cards, 2,352 SpanishDict meanings and exactly 600 examples.
  Every example and meaning remains explicitly unassigned; no WSD, fallback or
  active-pointer change occurred.

## Not started

- Produce the French assignment bundle in the separate WSD task and import it
  through the immutable Stage 04 boundary.
- Pinned French embedding/reranker models, WSD, calibration, and selection.
- Production release generation and full French inventory integration.
- Activate and audit the inactive Spanish candidate in the actual app. Full
  corpus-frequency compilation and raw reharvest remain optional experiments.
- Release diagnostics and release-frozen resume behind the transplanted app.
- Artist mode.

The existing Fluency repository's local Apps Script and matching client were
updated for schema compatibility, but nothing was remotely deployed. No old
French deck data is an input to the clean pipeline. The active local candidate
uses the fresh Tatoeba run and makes no WSD or corpus-coverage claims.
