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
  Every example and meaning remains explicitly unassigned; no WSD or fallback
  occurred. The release is active only in the local workspace, and the current
  development server returns 200 cards and 600 examples through the ordinary
  Spanish app aliases.
- Gate 29 (Spanish app activation): enabled Spanish in the real transplanted
  language picker and connected it to the active release's study structure,
  manifest and composition aliases. The shell cache moved to `flashcards-v270`
  / `20260822h` so an older offline config cannot keep Spanish disabled. Browser
  verification selected Spanish and rendered ten dynamic levels, with Level 1
  exposing its first 20-card learning set from the active candidate release.
- Gate 30 (unassigned Spanish app audit): resumed the exact Level 1 / Set 1
  session, cycled all three retained OpenSubtitles examples, opened Card Data
  and reached the JSTA flag flow without sending a write. Removed the false
  `100%` presentation caused by normalizing a dictionary-only menu for stable
  navigation; unassigned groups now say `Unassigned`, while real assigned
  releases can still display evidence percentages. The shell cache moved to
  `flashcards-v271` / `20260822i`.
- Gate 31 (Spanish enrichment cut line): measured every mature optional layer
  against the 200-card candidate and recorded an explicit rebuild/defer/reject
  decision. In particular, the old ID-keyed clitic file is excluded because
  524 of 544 rows contain historical WSD assignments. Removed the runtime
  paths to old mutable conjugation, English-cue and mislabeled frequency files;
  the app now treats those capabilities as absent until a clean release selects
  typed replacements. No enrichment data was copied or activated. The shell
  cache moved to `flashcards-v272` / `20260822j`.
- Gate 32 (typed conjugation artifact): added the shared `conjugation-layer/v1`
  contract plus a Spanish Jehle source adapter. Pinned the exact 2.9 MB CSV as
  reconstructed source evidence and built content-addressed artifact
  `sha256:ac8df2688d427ac98b1b173c2d7d797e3cdc298d737bb4457afc91d2fb06a4ed`.
  It covers 30 of 60 requested verb/AUX headwords with 540 paradigms; all 30
  misses are explicit and no `verbecc`, old table, WSD assignment, release or
  fallback was used.
- Gate 33 (release-backed Spanish conjugations): selected the typed Jehle
  artifact in validated release
  `es-speech-audit-200-unassigned-jehle-20260822` and activated it only in the
  local workspace. The release still contains the same 200 surface cards and
  600 explicitly unassigned examples; no WSD was introduced. Its stable app
  alias now serves 30 headword tables from the immutable release composition.
  Browser verification opened `tener` through the existing card UI and rendered
  `tengo`, `tienes`, `tiene`, `tenemos`, `tenéis`, and `tienen`. Surface-only
  cards join the optional layer through their dictionary headword, and
  `SENSE_CYCLE` menus retain verb tools through `cycle_pos`. Missing tables
  continue to degrade to the existing external reference rather than an old
  local file. The shell cache moved to `flashcards-v275` / `20260822m`.
- Gate 34 (pre-Artist Speech parity): identified and fixed a source-isolation
  bug in the transplanted app's global examples cache. Switching Spanish to
  French could reuse the wrong split file and render a valid French card with
  no examples. Example data is now tagged by source path and cleared with
  language-scoped conjugation/cue state whenever the language changes. Browser
  verification resumed French, displayed all three Tatoeba examples, switched
  to Spanish and displayed all three OpenSubtitles examples, then switched back
  to French and retained the correct Tatoeba card. JSTA Card Data, explicit
  `Unassigned` labels and release-owned levels remained intact. English
  production cues were deliberately deferred because the clean candidate has
  zero morphology rows, so a cue table would be unused dead weight. The shell
  cache moved to `flashcards-v276` / `20260822n`. Artist migration now has no
  remaining Speech-architecture blocker.
- Gate 35 (immutable Artist catalog): added typed Lyrics manifest and
  composition contracts plus build, validation, activation and read-only app
  routing. Locally active release `lyrics-legacy-parity-20260822` freezes five
  configured Spanish/French sources into exactly 36 hashed app files without
  copying the old mutable `Artists/` tree or deleted monoliths. It contains
  21,678 source-card rows and records historical assignments honestly as
  retained parity outputs rather than clean WSD results. The browser validates
  the catalog before use, loads release/layer provenance for audit flags and
  bypasses both current and pre-migration service-worker catalog caches. Bad
  Bunny's 295-song setup, a 20-card Learn set, lyric display, all-example Card
  Data, custom one-song deck construction, French no-song/no-art degradation
  and return to Speech all passed in the transplanted product UI. The obsolete
  Artist monolith variant branch was removed. Shell cache moved to
  `flashcards-v278` / `20260822p`.
- Gate 36 (clean one-song learner preview): packaged the clean `Estamos Arriba`
  assembly as validated inactive release
  `lyrics-clean-estamos-arriba-preview-20260823` with 162 exact surface cards,
  349 selected examples and six hashed app files. The active pointer remains on
  `lyrics-legacy-parity-20260822`. The real learner UI browser-verified the
  one-song catalog, release-derived levels, 17-card Learn set, WSD sense,
  available and missing translations, all ten `arriba` examples, and exact
  unfinished-set resume. Preview selection now uses release-versioned asset
  URLs; saved Lyrics sessions carry their release ID; release-mismatched legacy
  sessions cannot contaminate a preview. Resume also now tolerates the intended
  lazy absence of examples before the first deck load. Card Data now provides
  an example-first expandable drilldown of every occurrence's complete typed
  lineage plus its raw future-proof record; the clean multi-sense `que` card
  was browser-verified end to end. The flag dialog visibly confirms its exact
  preview release and source run without requiring a submission, empty Review
  degrades to Learn-only, and switching back to Spanish Speech preserves its
  independent 20-card set. Shell cache moved to `flashcards-v284`.
- Gate 37 (full Spanish Lyrics source boundary): added an adapter-based,
  no-execution corpus planner and pinned translation-aware plan
  `es-parity-source-plan-20260823-v2`. It selects exactly 914 artist-scoped
  songs from the four Spanish parity sources across 69 content-addressed files,
  records J Balvin and Rels B as explicit exclusions, and preserves seven
  cross-source song collisions. Optional translation coverage is explicit:
  Bad Bunny 190/537, Rosalía 92/241, Young Miko 0/105 and test playlist 22/31.
  No song ingest, routing, WSD, deck, release or activation ran.
- Gate 38 (resumable Lyrics corpus ingest): added a bulk executor that consumes
  only the verified objects named by a corpus plan and parses shared batch and
  translation snapshots once. It creates the normal immutable source-ingest
  run for every artist-scoped song, reports progress, and safely resumes only
  after verifying exact artist/song/source/translation identities, stage
  references, completion state and all output hashes. A deterministic corpus
  completion record is emitted only when the whole plan verifies. Fixture
  coverage proves optional translation materialization, an all-skip rerun and
  conflict detection. The real command then created and verified all 914 song
  runs. Samples across every artist confirmed full, partial and absent optional
  alignments. No routing, WSD, deck, release or activation was performed.
- Gate 39 (artist-scoped corpus processing boundary): added a resumable bulk
  runner over the existing tokenization, normalization, elision-restoration and
  live-routing implementation. Immutable profile
  `es-live-routing-v1-20260823` pins nine shared language resources plus the
  distinct capitalization statistics and legacy routing comparator for each of
  the four sources; Bad Bunny evidence cannot leak into another artist. Heavy
  resources are cached per artist profile, typed overrides remain artist/song
  scoped, and the historical routing snapshot is comparison evidence only.
  Exact input, implementation, stage-reference and output-hash validation gates
  resume and final completion. Both one-song and corpus interfaces, safe resume
  and corruption rejection pass in the 190/190 suite. The real 914-song
  processing run completed all 361,713 analysis units from scratch; no menu,
  WSD, deck, release or activation ran.
- Gate 40 (normalized corpus lexical menus): loaded the pinned SpanishDict
  snapshot once over the exact 14,938-form routing union and built verified
  compact menus for all 914 songs. Occurrence candidates now retain stable
  analysis IDs and counts rather than duplicating complete sense trees; WSD,
  validation, consolidation and audit consumers resolve the authoritative menu
  and fail on drift. The real corpus contains 277,335 ready, 34,621 no-menu,
  40,827 ineligible and 8,930 review requests. No sense was assigned.
- Gate 41 (corpus WSD boundary): prepared all 361,713 occurrence-level WSD
  requests through one safe resumable command in 23 seconds. Exactly 277,335
  are executable and 82,687 carry optional aligned translations. The current
  WSD method remains deliberately external and unsettled; no model ran and the
  active Lyrics parity release did not move.
- Gate 42 (immutable static deployment candidate): active and preview Artist
  catalogs now bind every data/media path to their exact release URL. Built
  inactive candidate `fluency-next-local-candidate-20260823` from the selected
  Spanish Speech, French Speech and Lyrics parity releases: 91 hashed files,
  75,642,859 bytes and three integrity-checked offline-download scopes. Backend
  secrets, docs and the development lineage explorer are excluded. An ordinary
  static HTTP server returned the shell, configs, manifests and representative
  Spanish, French and Bad Bunny assets without workspace routing. Nothing was
  deployed or activated. Shell cache moved to `flashcards-v285`.
- Gate 43 (WSD-last downstream contracts): added an algorithm-neutral complete
  corpus result catalog and resumable bulk import. It requires one exact bundle
  for every planned song, one method profile, matching plan/menu/request hashes
  and complete per-song outcomes. Added the following resumable corpus
  consolidation command with an independently hashed example-selection policy
  and exact upstream/output verification. Neither command needs to know how the
  assignments were produced. They are implemented and tested but deliberately
  unexecuted until a full WSD catalog exists.

## Not started

- Produce the French assignment bundle in the separate WSD task and import it
  through the immutable Stage 04 boundary.
- Pinned French embedding/reranker models, WSD, calibration, and selection.
- Production release generation and full French inventory integration.
- Full corpus-frequency compilation and raw reharvest remain optional.
- Scale the clean one-song Lyrics release path to the full Spanish Artist corpus;
  the active parity release still intentionally retains current materialized
  outputs until that comparison is reviewed.

The existing Fluency repository's local Apps Script and matching client were
updated for schema compatibility, but nothing was remotely deployed. No old
French deck data is an input to the clean pipeline. The active local candidate
uses the fresh Tatoeba run and makes no WSD or corpus-coverage claims.
## Gate 44 — WSD branches and corpus Artist assembly

- Full-corpus WSD, consolidation and app outputs are keyed by exact method
  profile instead of competing for one mutable per-song stage path.
- Source ingestion, routing, lexical menus and prepared contexts remain shared
  immutable inputs across WSD experiments.
- A resumable corpus assembler merges exact song assemblies into per-artist
  split assets and one language surface-card master, with stable sense alignment
  and explicit empty buckets for artist-absent senses.
- Two-artist fixture coverage proves that the shared master cannot shift one
  artist's example buckets onto another artist's sense.
- The operation is inactive: it cannot compose or activate a Lyrics release.
## Gate 45 — Inactive clean corpus release composition

- Clean assignment assets are composed only from one exact method branch.
- Optional songs, albums, artwork, themes and Spotify metadata are retained
  from one explicitly named parity release and content-bound in composition.
- Song `cardIds` are replaced by the clean assembly's membership; historical
  assignments cannot leak through the retained media catalog.
- A candidate comparison reports card, sense/frequency, example, translation,
  song-coverage, optional-media and payload changes before activation.
- Release validation runs before publication and the builder never writes
  `active.json`.
## Gate 46 — Resumable best-so-far corpus WSD execution

- The current pinned Spanish v5 method can execute the full prepared Lyrics
  corpus as an explicitly provisional method branch.
- spaCy, BETO, prototypes and calibration assets load once per invocation.
- All Gemini requirements are collected before the first result bundle is
  published, keeping the shared branch delta content-stable across resumes.
- Existing song bundles are checked against their exact requests, menus and
  method before being skipped.
- Completion emits the provider-neutral bundle catalog required by the
  method-branch importer; it still cannot import, compose, or activate a deck.
## Gate 47 — Preserved Artist baseline audit labelling

- The retained parity release is the initial migrated Artist dataset; a full
  clean WSD rerun is optional research work rather than a migration blocker.
- Card Data now identifies the exact release supplying historical examples and
  labels prompt IDs missing from the new registry as historical retained
  assignments instead of presenting them as broken/unregistered models.
- Existing per-example method, song, translation and raw-record evidence stays
  visible, while future clean records continue to expose their deeper run and
  occurrence lineage automatically.
## Gate 48 — Bounded learner-app and offline acceptance

- Bad Bunny, Rosalía, Young Miko and French Artist releases, whole-artist and
  custom-song sources, Learn, Review, resume, completion and Card Data were
  exercised against the real local app.
- JSTA saved a three-song cross-artist selection and the deployed SongSets v2
  endpoint returned its exact song IDs and contributing artist slugs. A fresh
  login restored the same selection after the post-login reconciliation fix.
- French Lyrics is reachable from the language-first chooser without an
  unnecessary Speech load.
- The explicit immutable Lyrics download now supports an offline active-alias
  fallback without caching or silently substituting the mutable alias itself.
  Bad Bunny rendered with the static server stopped.
- Preview-to-active Lyrics release switching passed without changing an active
  manifest.
- The deliberate JSTA flag is confirmed in FlaggedWords with its exact release,
  run, client build and non-empty provenance JSON.
- Final inactive candidate `fluency-next-acceptance-candidate-20260823-v5`
  contains 91 hashed files and 75,661,383 bytes. It is not deployed.
- Production cutover remains blocked only by the explicit per-deck
  clean-versus-retained data decision and subsequent deployment approval.
