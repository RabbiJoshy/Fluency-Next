# Artist/Lyrics mode migration

## Outcome

Artist mode is migrated as a product-parity release boundary, not as another
copy of the mutable legacy `Artists/` tree. The existing Fluency UI, playback,
song selection, progress identities, Card Data view and shell mechanics remain
the product baseline. The new architecture controls exactly which materialized
Artist outputs that UI can see.

The locally active audit release is:

- release: `lyrics-legacy-parity-20260822`
- location: `<workspace>/releases/lyrics/lyrics-legacy-parity-20260822/`
- sources: Bad Bunny, Rosalía, Young Miko, Joshua's Spanish test playlist and
  the French test playlist
- languages: Spanish and French
- total source-card rows: 21,678
- app files: 36 exact, hashed files (65,069,572 bytes)
- assignment status:
  `historical_materialized_assignments_preserved_for_product_parity`

This is sufficient to continue with the app and Artist pipeline audit. It does
not claim that the historical Artist assignments were produced by the clean
Speech WSD method.

## Folder and routing contract

The code repository owns contracts and app code only:

```text
src/fluency/artist/
  release.py                 build, validate, activate and resolve catalogs
src/fluency/lyrics/
  records.py                 stable song, line and optional alignment identities
  lineage.py                 append-only typed pipeline events
  ingest.py                  immutable source-ingestion stage and legacy adapter
  process.py                 shared token occurrence and analysis-unit runner
  routing.py                 explicit migration-snapshot routing adapter
  overrides.py               one typed, scoped human-override registry
  languages/
    base.py                  common normalization adapter contract
    spanish.py               Spanish elision and normalization policy
    spanish_routing.py       ordered Spanish routing policies and evidence
schemas/
  lyrics-release-manifest.schema.json
  lyrics-release-composition.schema.json
  lyrics-lineage-event.schema.json      shared event vocabulary for every language
  lyrics-audit-bundle.schema.json       portable one-song audit payload
  raw-lyrics-song.schema.json
  lyrics-line.schema.json
  lyrics-line-alignment.schema.json
  lyrics-occurrence.schema.json
  lyrics-analysis-unit.schema.json
  lyrics-route-decision.schema.json
  lyrics-route-comparison.schema.json
  lyrics-routing-overrides.schema.json
app/
  config/artists.json        empty static fallback only
  lyrics-audit/              development-only lineage explorer
```

Generated data remains outside git:

```text
<workspace>/releases/lyrics/
  active.json
  <release-id>/
    manifest.json
    composition.json
    app/
      config/artists.json
      Artists/
        spotify_tracks.json
        es/
          vocabulary_master.json
          <artist>/index.json
          <artist>/examples.json
          <artist>/songs.json          optional
          <artist>/albums.json         optional
          <artist>/Images/*            optional
        fr/
          vocabulary_master.json
          <artist>/index.json
          <artist>/examples.json
```

The app keeps its familiar stable URLs. The local server resolves
`/config/artists.json` and `/Artists/*` through `active.json`. The service
worker never caches those mutable aliases, so activating another exact release
cannot silently blend it with the old one. The catalog request also has a
one-time contract query key to escape the old application's cached empty
catalog during migration.

## What was retained

Only files referenced by the reviewed artist catalog were retained:

- split indexes and split example maps;
- language vocabulary masters required to reconstruct the app cards;
- song catalogs used by whole-artist and custom-playlist selection;
- album dictionaries, referenced artwork and the Spotify track map;
- historical assignment fields and their available prompt/run sidecars;
- the existing progress, selected-song and selected-artist identity contracts.

Each index must have unique card IDs and exactly the same ID set as its example
map. Every emitted app file is declared by path, byte size and SHA-256 content
identity. Catalog entries carry the active release ID and manifest/composition
paths, so audit flags can identify the release and Artist source layer.

## What was cut

The migration does not copy:

- the legacy mutable `Artists/` directory into the code repository;
- deleted or debugging monoliths;
- alternate `?variant=` monolith loading;
- unreferenced artwork and intermediate pipeline folders;
- preview files, notebooks or source-specific build dependencies;
- an implicit fallback to a prior Artist release;
- a claim that historical assignments are clean or current WSD results.

The old French config referred to a deleted monolith. The importer resolves its
existing split index/examples pair and does not recreate the monolith.

## Product-parity verification

The local app was verified through:

1. Spanish Speech to the Lyrics source picker.
2. Bad Bunny setup with 295 songs, artwork, percentage levels and stable sets.
3. A 20-card Learn set, card flip, lyric example and all example metadata in
   Card Data.
4. Choose-your-own mode across the available Spanish artists, selecting one
   song and rebuilding a 14-card deck.
5. French Artist setup with no song catalog or artwork; both optional fields
   degrade cleanly while its 1,455-card source remains usable.
6. Switching back to Speech without changing either Speech release.

## Lineage explorer checkpoint

The first end-to-end audit slice uses Bad Bunny's `Estamos Arriba` and compares
two preserved normalization runs. It contains the whole song (61 lines and 585
stable occurrences), highlights 84 direct changes, and connects the selected
token to the current routing and immutable app-release snapshots wherever a
safe identity join exists.

The explorer deliberately does not invent missing history. Direct claims,
reconstructed lookups, materialized snapshots and future human-review claims
are different evidence kinds in the contract. A token without a safe join says
so. This fixture is the reference UI for the new pipeline, not a replacement
for the learner-facing app.

The generic stage vocabulary is: acquire, extract, align, normalize, tag, route, menu,
assign, consolidate, assemble and review. Language-specific behavior belongs in
adapter metadata and decision payloads, so Spanish elision restoration does not
become a required French, Portuguese or Dutch pipeline stage.

The first clean source-ingestion runs are preserved under
`runs/es/lyrics/`. `bad-bunny-estamos-arriba-source-v1` proves that a missing
song in the historical aligned-translation file degrades to 61 valid source
lines and zero translations. It was not overwritten.
`bad-bunny-estamos-arriba-source-v2` uses the separately preserved flat
translation map and emits 61 lines, 43 optional alignments, 18 explicit
alignment absences and 105 lineage events. Both raw legacy inputs are pinned by
content identity in the workspace object store. No routing, WSD, deck or active
release changed.

`bad-bunny-estamos-arriba-source-v7` is the verified clean processing and live-routing checkpoint. It
emits 585 exact-span token occurrences, 585 normalized analysis units, 585
route decisions and 1,755 lineage events. Tokenization, Spanish elision restoration,
and word routing are recomputed directly from pinned inputs. The old
`word_routing.json` is retained only as an explicitly identified comparator.
Every word records the complete ordered policy trace, the inputs each policy
consulted, its final reason, and the exact artifact IDs. Against the mature
Spanish normalization overlay it matches
574 of 585 occurrences (98.12%). The eleven differences are ten newly handled
leading-aphesis occurrences (`'Tamo` to `estamos`) and one preservation of
`Yeh` where the old overlay inherited `eh`. The lineage explorer now exposes
this clean processing record for every token, including the old-versus-clean
routing decision and every passed or matched policy.
The development bundle keeps occurrence-specific route IDs but stores each
identical routing decision/policy trace once as a normalized-form profile, so
the extra auditability does not duplicate the same trace hundreds of times.

The same run now also contains an immutable provider-neutral lexical-menu
layer. All 585 analysis units remain visible: 463 have one or more menu
analyses, 59 are explicit `no_menu` records, 45 are route-ineligible and 18 are
held for proper-name review. The 203 attempted lookup forms are resolved from
the pinned SpanishDict snapshot through the shared Speech adapter. Surface card
identity remains separate from lookup identity (for example, `líbrame` may
look up `librar` without becoming the `librar` card). No WSD, deck assembly,
release or activation occurred. Auditor v9 exposes every analysis and sense
leaf, plus an exact 59-token no-menu filter.

The next immutable output, `stages/04_wsd_prepare`, now binds all 585 units to
their exact lyric line, token span, lexical candidate and optional aligned
translation. It produces 463 executable requests, while retaining the 59
no-menu, 45 ineligible and 18 review requests as non-executable records. The
request contract is mode-neutral: Lyrics targets an `analysis_unit`; Speech can
target a `sentence_candidate` without inventing one mode's identity in the
other. The explorer shows a separate **Disambiguate sense** stage with
`Prepared — model not run`, so menu availability cannot be mistaken for a WSD
assignment.

The clean router deliberately does not import the legacy scattered noise,
proper-name, English or cognate override lists as truth. Unknown forms remain
visible in `sense_discovery`; capitalization-only proper-name evidence becomes
an explicit review candidate rather than a silent exclusion; interjection-only
lexical entries have their own spoken-particle disposition. Any future manual
decision must live in `config/lyrics/routing-overrides.json` with an ID, reason,
author, timestamp and scope. The registry is empty by default, and conflicting
active entries fail loudly.

## Continuation handoff: remainder of the migration

This section is the authoritative continuation plan. A new agent should start
here rather than infer the remaining work from chat history. The completed
implementation checkpoints are commits `d4f2810` (source lineage), `a9c83e5`
(clean processing lineage), `d75403d` (direct live routing and policy-trace
auditing), `3f3c018` (provider-neutral lexical menus), `984ab9a`
(mode-neutral WSD preparation and auditor v9), and `88fff5c` (auditable
Spanish v5 Lyrics execution and complete-result import). The verified run is
`runs/es/lyrics/bad-bunny-estamos-arriba-source-v7` in the external workspace.

Environment map:

- new code repository: `/Users/joshuathomasamar/PycharmProjects/Fluency-Next`;
- legacy reference repository: `/Users/joshuathomasamar/PycharmProjects/Fluency`;
- generated-data workspace: `/Users/joshuathomasamar/PycharmProjects/Fluency-Workspace`;
- current auditor: `http://127.0.0.1:4173/lyrics-audit/?v=9` when serving
  `Fluency-Next/app` on port 4173;
- active parity release:
  `Fluency-Workspace/releases/lyrics/lyrics-legacy-parity-20260822`.

Before editing, run `git status --short`, read this file, inspect commits
`d4f2810`, `a9c83e5`, and `d75403d`, and run
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3.12 -m unittest discover -s tests -p 'test_*.py'`.
The checkpoint has 182 passing tests. Treat the legacy repository as a source
of behavior and retained artifacts, not as the destination for new code.

### Non-negotiable constraints

- Preserve the existing learner-facing app behavior and layout. Refactoring the
  implementation is welcome; redesigning the product is a separate, explicit
  decision. The development-only lineage explorer is not the learner app.
- Spanish card identity is surface-based. Do not quietly restore lemma-indexed
  cards. Lemmas and dictionary headwords are nullable analysis metadata.
- Never overwrite a run or release. A changed input, policy or implementation
  creates a new immutable run. Activation selects one exact release; it never
  merges that release with old assignments.
- Generated data belongs in `Fluency-Workspace`, not the code repository. The
  repository owns runners, adapters, schemas, small audit fixtures and app code.
- Every output must name its exact inputs, implementation/method, run and
  evidence kind. Missing data is represented as an explicit nullable field or
  abstention, not guessed. Historical snapshots must be labelled snapshots.
- Shared engines are language-agnostic. Language quirks belong in adapters and
  configuration. Artist mode and Speech mode should reuse contracts where the
  underlying decision is genuinely the same.
- Do not wait for the final WSD research decision. Build a typed WSD boundary
  that can accept the current best Spanish method and later replace it without
  changing token, route, deck or app contracts.
- Keep the retained Spanish harvested sentences and Gemini embeddings. Discard
  stale assignments freely because they are cheap to reproduce. Never mix
  assignments from two runs implicitly.
- Give Joshua commands for genuinely long harvesting, embedding or WSD runs.
  Quick schema, import, parity and unit checks should be run by the agent.

### What is already complete

1. The old learner app shell and Artist behavior have a local parity release,
   including song selection, custom playlists, progress identity, artwork,
   playback metadata and Card Data.
2. Artist release selection is exact and fail-closed. Stable app URLs resolve
   through one active manifest without silently falling back to an old release.
3. Raw song acquisition, line extraction and optional translation alignment
   have typed records, stable identities and direct lineage.
4. Shared Unicode tokenization now emits exact-span occurrences. Spanish
   normalization/elision restoration is isolated behind a language adapter.
5. Normalized analysis units and route decisions have explicit schemas. The
   clean Spanish router recomputes every decision from pinned automatic evidence;
   the legacy routing snapshot is comparison evidence only.
6. The multi-song auditor exposes source, alignment, legacy run comparison,
   clean recomputation, routing provenance, lexical menus and current release
   assignments, degrading explicitly when a song only has legacy evidence.
7. The Google Apps Script changes made earlier in the migration preserve flag
   run/release provenance, playlist selection and `JSTA` audit privileges.

### Remaining work, in execution order

#### 1. Port the live word-routing engine — complete

Replace `RoutingSnapshot` as the decision-maker with a shared deterministic
router that consumes normalized analysis units plus pinned resources. Preserve
the snapshot adapter only as a baseline comparator.

The shared router should express generic dispositions such as normal
vocabulary, conjugation, derivation, clitic/compound handling, proper noun,
foreign language, noise, low-frequency exclusion, review and unresolved.
Spanish-specific proper-name, clitic, surface-form and lexical rules belong in
`src/fluency/lyrics/languages/spanish.py` or a sibling Spanish routing adapter.
Do not turn Spanish categories into required categories for French, Portuguese
or Dutch.

Required outputs:

- one route decision per analysis unit, including selected bucket, optional
  target, confidence/evidence, reason codes and all consulted artifact IDs;
- direct route lineage rather than `materialized_snapshot` evidence;
- a parity report against the pinned `word_routing.json`, with every difference
  grouped as intended, regression, newly resolved or previously stale;
- explicit unresolved and review outputs that continue through the audit path.

Acceptance gate passed in `bad-bunny-estamos-arriba-source-v7`: all 585
occurrences are accounted for across 237 distinct forms. The comparator groups
208 matches, four intentional removals of the old low-frequency drop, one newly
resolved form and 24 review-required differences. The auditor displays the old
snapshot beside the clean route and expands every evaluated policy. No WSD,
deck assembly or release activation occurred.

#### 2. Generalize the auditor to multiple songs and run comparison

Do this after clean routing so the UI is built around the final pre-WSD record
shape. Replace the hard-coded `estamos-arriba.json` assumption with a small
auditor catalog and song selector. It must support at least two songs from one
artist, then songs from different artists/languages without changing the UI.

The first multi-song slice is complete: the catalog and selector safely switch
among `Estamos Arriba`, `MONACO` and `Yonaguni`, validate bundle/song identity,
update the URL, and state the available evidence per song. Only `Estamos
Arriba` currently has clean processing lineage. Cross-run selection, token
history and cross-artist/language fixtures remain part of this work package.

For a selected song, retain the whole-song token map and token drawer. Add:

- selection of baseline and candidate run where both contain that song;
- filters for route changes, normalization changes, proper names, noise,
  unresolved items, WSD changes and release inclusion;
- a compact per-song summary of added, removed and changed decisions;
- a token history view showing its records across runs without pretending that
  unrelated occurrence IDs are identical;
- graceful messages when a run lacks translations, artwork, playback, routes,
  menus, WSD or final assignments.

Keep this auditor as a development tool under `app/lyrics-audit/`. Do not merge
its interface into the learner app unless Joshua explicitly chooses elements.

Acceptance gate: switching songs and runs must not reload or blend the wrong
bundle, and every displayed value must expose its evidence boundary.

#### 3. Build the lexical-menu boundary — complete

For analysis units routed to vocabulary/WSD, create a language-neutral lexical
candidate contract. It should carry the surface occurrence, normalized form,
optional lemma, optional dictionary headword, POS analysis and sense-menu
leaves. No field other than the surface occurrence identity should be assumed
to exist in every language.

Reuse the mature Speech menu architecture where possible:

- Spanish can use SpanishDict-compatible headword/POS/sense leaves;
- French can use Kaikki/Wiktionary headword/POS/sense leaves;
- future providers plug in through adapters without changing downstream WSD;
- menu providers may propose lookup headwords but may never replace the Spanish
  surface-card identity;
- missing/ambiguous menus produce review or abstention records, not dropped
  tokens.

Acceptance gate: the same generic menu record validates for SpanishDict and
Wiktionary examples, including empty optional fields.

Acceptance gate passed in `bad-bunny-estamos-arriba-source-v7`. The shared
contract was exercised with SpanishDict and Kaikki/Wiktionary fixtures; nullable
lemma/headword/POS fields remain metadata, while surface identity is required.
The real Spanish run produced 585 occurrence-bound candidates, 960 attached
analyses and 5,409 sense leaves. Missing menus and route abstentions are typed
records, and the explorer states prominently that none of the menu options has
been selected by WSD.

#### 4. Add WSD as a replaceable stage

Port the current best Spanish embeddings-based WSD exactly as it exists when
this step begins. Do not use this migration to re-litigate model quality. The
stage consumes routed analysis units, lexical menus, sentence/song context and
the retained embedding artifacts. It emits assignments or explicit
abstentions with scores, selected menu leaf, headword/POS analysis, method ID,
configuration identity and input artifact IDs.

The WSD runner must be shared with Speech where feasible, with language
adapters for menu shape, clitics, lemmatization/alignment and other real
language differences. Lyrics-specific context assembly belongs in a mode
adapter rather than the scoring core.

Required safeguards:

- no assignment from another run can enter the output unless explicitly named
  in a composition manifest;
- embeddings are joined by content/stable identity, never filename alone;
- a missing embedding, menu or confident sense degrades to an auditable
  abstention;
- rerunning WSD creates a new stage/run and leaves tokenization, normalization
  and routing artifacts reusable when their inputs are unchanged.

Acceptance gate: run a small real-song sample, inspect changes in the auditor,
and verify that activating nothing leaves the learner app on the parity release.

Preparation checkpoint complete: the generic v2 request contract and Lyrics
context adapter are implemented and exercised across the full song. Exact span
validation fails closed, translations are nullable, and the source/menu
artifacts are content-bound. No model had run at that checkpoint; the execution
boundary described below supersedes its former remaining-work note.

Execution boundary checkpoint (2026-08-23): the exact v5 method commit and
shipped defaults are pinned. Shared orchestration now exposes a language policy
seam; Spanish supplies the measured `0.02 * 0.5^rank` menu prior, bridged
occurrence-POS filter, conservative `se` gate and renderable-leaf repair. The
BETO prototypes and legacy calibrator are preserved byte-for-byte with
reconstructed provenance; old assignments and the old context-token cache are
excluded. BETO occurrence vectors are regenerated from exact request spans.

Lyrics has a complete result-bundle/import contract requiring one typed result
for every one of the 585 requests. Assigned results must bind to the exact
analysis and sense in the lexical artifact; all 59 no-menu, 45 ineligible and
18 review records must remain explicit; partial, stale or invented selections
fail before publication. Alignment and generative escalation remain ported
options but disabled, matching the latest shipped base run. The real executor
is ready and finds only 100 Gemini exact-text cache misses (55 new lyric lines
plus 45 menu strings); the retained cache itself remains immutable and misses
are written to a run-scoped delta.

This checkpoint is committed as `88fff5c` (**Port auditable Spanish v5 lyrics
WSD**). It changes no active learner release.

Real-song acceptance checkpoint (2026-08-23): the complete inactive
`Estamos Arriba` run now contains all 585 typed WSD results: 463 assignments,
59 explicit `no_menu` outcomes, 45 route-ineligible outcomes and 18 review
outcomes. The executor reused retained Gemini embeddings and wrote only its
exact cache misses to the run-scoped delta. Auditor v10 resolves each result
back to its occurrence, menu analysis and sense leaf, and exposes the selected
tuple, decision path, score evidence, method and stable IDs. Browser validation
confirmed the 463-assignment count and a complete token trace with no console
errors. No learner release was built or activated.

#### 5. Consolidate occurrences into Artist cards and examples

Build the clean equivalent of the old Artist assignment/consolidation layers.
This converts per-occurrence WSD output into the existing split app contract:
artist `index.json`, `examples.json`, language `vocabulary_master.json`, and
optional song/album/media files.

Rules:

- cards remain surface-based for Spanish;
- every example retains song, artist, line, translation, source, occurrence,
  normalization, route, menu, WSD and run/release provenance where available;
- repeated occurrences may consolidate into one card/sense, but their lineage
  remains separately inspectable;
- proper nouns, noise, exclusions and abstentions remain reportable even when
  they do not become study cards;
- ordering and example caps are explicit policies recorded in the run;
- optional translation, artwork, Spotify/timestamp data and albums may be empty
  without invalidating the deck.

Acceptance gate: the clean sample validates against the same app-facing schema
as the parity release and Card Data can scrub all metadata for every example.

Core consolidation checkpoint (2026-08-23): the shared, language-neutral
consolidator now consumes the exact source, occurrence, route, menu, WSD and
method artifacts and fails if any cross-stage identity or content binding has
drifted. For `Estamos Arriba` it emits 162 surface cards, all 463 assigned
occurrences as lossless examples, and one typed disposition for every one of
the 585 analysis units. The explicit selection policy retains 349 unique-line
examples for study (maximum 12 per exact sense) without deleting the remaining
occurrence history; all 122 non-assigned outcomes remain auditable. English is
the configured display translation, missing translations are valid, and all
available language alignments remain attached. Auditor v11 exposes both an
included card candidate and the explicit non-study state for any selected
token. The browser reports 162 clean cards and no console errors.

The provider-neutral consolidation and app-assembly halves of this section are
now complete. The inactive app assembly contains an exact 162-ID intersection
across `index.json`, `examples.json` and `vocabulary_master.json`, with 349
selected examples in sense-aligned buckets. Every example carries its run,
occurrence, analysis-unit, route, lexical-candidate, menu, WSD result, source
snapshot and optional alignment provenance. Of those examples, 297 have an
English alignment and 52 degrade to an empty translation. All 162 clean surface
words already exist in the parity vocabulary; the clean one-song policy selects
243 more examples than the parity release currently exposes for this song.
That difference is reported for review, not silently blended.

Inactive-preview checkpoint (2026-08-23): release
`lyrics-clean-estamos-arriba-preview-20260823` packages that exact payload with
one pinned parity song record and optional Spotify mapping. It validates as six
hashed app files (968,145 bytes), remains explicitly inactive, and leaves
`active.json` on `lyrics-legacy-parity-20260822`. The real learner app can open
the release directly through `lyricsRelease=...`: its one-song catalog, 162
surface cards, release-derived levels, 17-card first Learn set, real sense
assignment, translated/translation-missing examples and all ten selected
examples for `arriba` render correctly. Release-bound unfinished-set resume was
added and browser-verified back to the exact `arriba` card. That test also fixed
an old lazy-data bug where restoring selected songs validated a not-yet-loaded
examples payload and left the loading screen stuck.

The example-first UI acceptance check is complete. Card Data groups records
under their assigned senses, gives every example its own expandable row, and
shows run, occurrence, analysis-unit, route, lexical-candidate, menu, sense,
WSD request/result/method/path, source, alignment, translation, song and
vocalist identities. A nested raw-record view guarantees newly added optional
fields remain inspectable before a tailored presentation is written. The clean
`que` card was browser-verified across six senses and all of their examples.
The flag dialog also shows the exact release and selected-example run that will
be attached before submission; no audit flag was sent during migration testing.
Returning from the preview to Spanish Speech preserved its independent
20-card set structure, and the preview's empty Review queue degraded to a Learn
action without inventing review cards.

#### 6. Compose and compare a clean immutable Artist release

Create a new release; never alter `lyrics-legacy-parity-20260822`. Its
composition manifest must name the exact source, processing, routing, menu,
WSD, consolidation and media artifacts used.

Produce a release comparison covering:

- cards/examples added, removed and changed;
- per-song coverage and exclusions;
- sense-assignment and route changes;
- missing optional media/translation fields;
- orphaned files, duplicate IDs and index/examples mismatches;
- payload size and app-load regression.

Only after the report is reviewed should the clean release be activated
locally. Keep rollback as a one-manifest selection back to the parity release.

Acceptance gate: exercise whole-artist mode, choose-your-own playlist, Learn,
Review, resume, completion, Card Data, flagging and progress persistence. Switch
back to Speech and confirm its active release and state are unchanged.

#### 7. Perform the bounded learner-app audit

This is a cleanup/parity audit, not a redesign. Remove dead branches that are no
longer reachable under the new contracts, consolidate duplicate loaders and
make schema failures visible. Prefer optional typed fields and explicit UI
fallbacks over provider- or language-specific conditionals.

Specifically verify:

- information remains available from the study-settings radial and the active
  card experience;
- Card Data is organized by example at the highest level and lets the user
  scrub every example's complete metadata;
- dynamic languages, levels, sets and Artist catalogs come from the selected
  release metadata;
- Learn/Review, unfinished-set resume and completion retain old behavior;
- empty translations, images, song lists, playback, menus, assignments or
  provenance render useful absence states rather than blocking the deck;
- flags include user, language, mode, card/example/occurrence IDs, run/release,
  stage/method and timestamp;
- `JSTA` sees admin information and flagging controls;
- playlist selection round-trips through the Google Sheet for each user.

Acceptance gate: compare the new app and legacy app side by side using a short
checklist. Any intentional product change must be listed separately from
migration parity.

#### 8. Scale the Spanish Artist run

After the truncated release is accepted, run the full Spanish Artist corpus
through the same immutable stages. Reuse unchanged source, translation and
embedding artifacts. Joshua should execute long WSD/embedding commands locally;
the agent should inspect manifests, reports and sampled auditor views afterward.

Do not activate merely because the run completed. Validate exact artifact
counts, sample multiple artists/songs, review differences from the parity
release and then explicitly choose the new release.

#### 9. Add further languages through adapters

Implement French first, then Portuguese and Dutch, without forking the pipeline.
Each language supplies only its real differences: tokenizer overrides if ever
needed, normalization/elision policy, lexeme resources, routing rules, menu
provider and WSD adapter. The shared occurrence, lineage, menu, assignment,
release and app contracts remain unchanged.

For each language, begin with a one- or two-song audit release. Missing artist
catalogs, translations, playback and artwork are valid. Do not require a
SpanishDict-shaped provider response from Wiktionary/Kaikki.

#### 10. Finish offline and deployment migration

Before making Fluency-Next the live repository:

- use release-versioned URLs for offline Artist assets rather than caching
  mutable active aliases;
- verify service-worker cache versioning and release switching;
- test the production Google Apps Script deployment with provenance flags,
  playlist memory and `JSTA` privileges;
- perform local and deployed smoke tests for Speech and Artist modes;
- create the new GitHub app/deployment only after local parity is signed off;
- retain the old repository/deployment as rollback until the new release has
  survived real use, then deprecate it explicitly.

### Immediate next action

Extend the same release composer and comparison report from one song to the
full clean Spanish Artist corpus rather than inventing a second packaging path.
Do not change `active.json`. A deliberate flag submission, non-empty Review
queue and completion/progress write remain production-backend checks, not
reasons to hold the clean data architecture in a one-song state.

The key separation is now enforceable: shell and study behavior can evolve
without rebuilding corpus data, while a new Artist data run can be activated
without changing the application or contaminating another run.
