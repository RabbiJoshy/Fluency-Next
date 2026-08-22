# Spanish Speech migration sub-roadmap

## Purpose

Move Spanish Speech from the existing Fluency repository into Fluency Next
without importing the old repository's mutable `Data/` tree, stale orchestration,
hidden fallbacks, or lemma-based identity. The result must preserve the real
Fluency product experience and existing learner progress while making every
inventory, corpus, menu, assignment, enrichment and release independently
replaceable and auditable.

This roadmap sits under Step 5 of `docs/ROADMAP.md`. It is a migration plan, not
an approval to choose every source or run every expensive stage in advance.
Josh and Codex stop at each decision gate below.

## Starting facts

- The live Spanish deck has about 10,000 ranked surface cards and currently
  publishes 10,749 compact index rows.
- Live Spanish card IDs already use the surface-only `surface/v2` scheme. Lemma,
  sense and POS changes must never mint a different learner card.
- Fluency Next also treats the surface as the card, but its canonical internal
  ID format differs. Existing progress therefore needs an explicit crosswalk;
  it cannot be assumed compatible.
- SpanishDict is the current best menu provider. Its stable leaves, headword,
  POS, gloss, context/usage notes and dictionary examples are valuable source
  evidence. The old compiled deck and inherited sense shares are not source
  truth.
- The latest WSD work is still experimental. Its current v5 stack is useful
  evidence, not a frozen migration dependency; its confidence calibration is
  known to be invalid for real speech.
- Fluency Next already accepts a complete external WSD bundle and can publish
  explicit unassigned examples. WSD can therefore attach later without
  blocking the rest of this migration.
- The old `run_normal_pipeline.py` is documentation of historical behavior, not
  an orchestrator to copy. It mixes old source assumptions, mutable paths,
  Wiktionary-era steps and final assembly decisions.

## Non-negotiable boundaries

- Surface form is card identity. Lemma remains lookup/display metadata only.
- No implicit union of runs, methods, sources or assignment layers.
- No old assignment or sentence silently enters a clean run.
- No generated output is written into the code repository.
- Every large input is a pinned snapshot in `Fluency-Workspace/raw/`.
- Every run and release is immutable; activation is manual.
- Missing WSD or optional enrichment remains visibly missing. It never triggers
  fallback to an old deck or old assignment.
- The existing live Spanish application remains untouched and usable until a
  separate cutover is explicitly approved.
- Expensive harvesting, embedding, model and full-deck commands are run by Josh
  locally after Codex provides the exact command.

## Approved preservation boundary

The migration preserves the existing harvested sentence bank and every paid
Gemini embedding, with explicit observed/reconstructed/unknown provenance. It
ports the current WSD method as versioned code plus required reproducibility
assets, but discards all of its generated assignments. Final example selection,
confidence decisions, compact decks and releases are rebuilt from scratch.

See `docs/migration/0004-spanish-speech-source-ledger.md` for exact files,
hashes, provenance gaps, the cross-language artifact contract and the dead
architecture that must not be reintroduced.

## Target folder shape

```text
Fluency-Next/
  config/
    pipelines/es/speech/
    inventory/languages/es-v1.json
    sense_menu/languages/es-spanishdict-v1.json
    harvest/languages/es-v1.json
    wsd/languages/es-v1.json
    enrichments/es/
  src/fluency/
    inventory/               # shared runner + Spanish frequency adapter
    sense_menu/               # shared contract + SpanishDict adapter
    harvest/                  # already shared; Spanish policy only
    wsd/                      # method-independent import boundary
    enrichments/              # typed optional Spanish layers
    release/                  # shared composition and app adapter
  docs/migration/
    0003-spanish-speech-migration-roadmap.md

Fluency-Workspace/
  raw/
    frequency/<pinned-spanish-snapshot>/
    spanishdict/<pinned-menu-snapshot>/
    opensubtitles/<pinned-es-en-snapshot>/
    wsd/<method-and-version>/
  runs/es/speech/<run-id>/stages/
  releases/es/speech/<release-id>/
```

## Migration sequence

### Phase 0 — Scope lock and read-only source audit

**Owner:** Codex. **Cost:** quick. **Status:** complete.

Inventory the current Spanish Speech system without copying it. Produce a
retain/rebuild/reject ledger covering:

- ranked surface inventory and frequency source;
- Spanish tokenization, accents, apostrophes and clitic forms;
- SpanishDict menu cache/snapshot and stable leaf IDs;
- sentence corpora, translations and provenance;
- current WSD inputs/outputs and prompt registry;
- morphology, clitic routing, conjugations, MWEs, usage notes, synonyms,
  cognates and personalised examples;
- compact app index/examples fields;
- progress IDs and alias history.

Each item is classified as source evidence to pin, behavior to reimplement,
derived output to rebuild, optional product layer to defer, or dead machinery to
leave behind. No data stage runs here.

**Exit:** Josh approves the ledger and the first genuinely ambiguous source
decision.

### Phase 1 — Identity and progress compatibility

**Owner:** Codex, decision with Josh. **Cost:** quick. **Hard gate.**
**Status:** canonical/alias direction approved, implemented and validated. App
read integration and any Sheet dry run remain later migration work.

Define one Spanish identity record containing the clean canonical card ID,
normalized surface key and every accepted legacy progress alias. Prove:

- lemma/POS/sense changes do not move a card;
- Speech and future Artist releases resolve the same surface card;
- old `es0<8-hex>` progress can resolve to the clean card;
- collisions and retired surfaces are explicit;
- migration is idempotent and dry-runnable before any Sheet write.

**Recommended direction:** retain the clean long canonical ID internally and
publish explicit legacy aliases/crosswalks, rather than making an old truncated
hash the new architecture's identity. This is not locked until Josh approves
the measured crosswalk and collision report.

**Exit:** 100% mapping report for every currently shipped Spanish surface, with
all exceptions named; no remote progress mutation.

The measured audit and two historical ID collisions are recorded in
`docs/migration/0005-spanish-progress-identity-audit.md`.

### Phase 2 — Spanish run profiles and language policies

**Owner:** Codex. **Cost:** quick. **Status:** complete 2026-08-22.

Add Spanish Speech rehearsal and audit profiles (20×3 and 200×3), then a full
profile later. Add configuration—not language forks—for:

- surface normalization and token boundaries;
- frequency adapter and exclusions;
- SpanishDict sense-menu behavior;
- corpus filtering and easiness policy;
- morphology/clitic lookup candidates;
- optional enrichment contracts;
- external WSD bundle requirements.

Planning a run must create only the immutable skeleton and execute no stage.

Implemented as shared configuration boundaries under `config/inventory/`,
`config/languages/es/`, `config/harvest/`, `config/sense_menu/`, `config/wsd/`
and `config/pipelines/es/speech/`. The Spanish profiles deliberately retained
an explicit inventory-source gate until OpenSubtitles was approved in Phase 3,
and retain `blocked_pending_assets` for WSD. These are visible gates, not fallbacks. The
current `sd-beto-cal-v5` method is identified at its audited source commit, but
no historical assignment is referenced and no model asset is claimed runnable
until its immutable migration is complete.

**Exit:** profiles validate, plan deterministically, and explicitly forbid lemma
identity, legacy inputs, fallback and automatic activation.

### Phase 3 — Fresh Spanish surface inventory

**Owner:** Codex. **Status:** complete 2026-08-22 using the approved recovered
surface ranking; optional full-corpus re-ranking is deferred.

Choose and pin the authoritative Spanish Speech frequency snapshot. Do not trust
the filename `SpanishRawWiki.csv`: its values currently mirror subtitle-style
counts, so its actual lineage must be established before reuse.

The full-corpus compiler exists for a future clean re-ranking experiment, but
it is not on the migration's critical path. The approved migration input is the
existing 9,999-surface `word_inventory.json`, copied into the workspace with
verified bytes and reconstructed provenance. Its list order and corpus counts
are retained; `known_lemmas` remain source evidence and are never imported into
card identity. Both fresh 20-card and 200-card inventories were built from this
one pinned snapshot without scanning or reharvesting OpenSubtitles.

Run 20 surfaces first, then 200. Emit ranked surfaces, frequencies, exclusions,
normalization evidence and the legacy-ID crosswalk. Lemmas from the old CSV may
be retained as lookup evidence only, never identity or ranking authority.

**Decision gate:** approve the frequency source and Spanish normalization rules.

**Exit:** immutable 200-card surface inventory with no duplicate normalized
surfaces, stable IDs and explicit rejected rows.

### Phase 4 — SpanishDict menu adapter and pinned snapshot

**Status:** complete for the 200-card audit on 2026-08-22.

**Owner:** Codex. The audit uses only the approved offline snapshot; no scrape
or download is part of this migration gate.

Port the best SpanishDict behavior into the shared sense-menu contract. Preserve
provider evidence rather than old assembly decisions:

- queried surface and returned headword;
- POS, stable sense ID, gloss and context;
- menu order as an explicit provider prior, not an observed corpus share;
- regions/register and construction/usage notes;
- dictionary examples and source linkage;
- redirects, conjugation mismatches, fuzzy corrections and no-menu outcomes.

Menus join to surface cards while allowing several headword/POS analyses. A
separate lookup-candidate layer may propose conjugation or clitic headwords; it
cannot replace the surface card.

**Decision gate:** resolved 2026-08-22. Pin the offline surface/headword caches
and morphology inputs; rebuild the menu per run without the scraper or old
normalized menu.

**Exit:** achieved by run `20260822T214657Z-db4c1b65`: 199 menus, one explicit
`no_menu` (`sr`), 474 analyses, 2,352 leaves, seven quarantined plural twins,
and zero network or fallback use.

### Phase 5 — Run-owned Spanish sentence harvest

**Owner:** Codex. **Status:** retained-bank adaptation complete 2026-08-22;
future full-corpus reharvest remains optional.

For the migration rehearsal, adapt the verified retained sentence bank and
candidate map into the shared harvest contract instead of rescanning the raw
corpus. Preserve every old sentence and its provenance as source evidence, but
rebuild run-owned matching, quality decisions and final selection. A future
fresh harvest may use the existing language-agnostic harvester. Prefer a
pinned aligned OpenSubtitles Spanish–English snapshot for this audit because it
provides conversational speech, translations, title/line provenance and the
parallel text used by current WSD research. Tatoeba remains a separately
selectable adapter; it is never silently mixed or substituted.

Retain a broad candidate pool per surface. Selection still targets three final
examples, but WSD does not participate in harvesting.

Runs `20260822T212608Z-702ef1b0` (20 cards) and
`20260822T212645Z-df19d6d0` (200 cards) rebuilt matching, quality scores and
candidate caps from the verified retained bank. They did not reuse old
candidate choices as final selections. The 200-card run retained 11,878
candidate assignments and 6,094 distinct sentences; every card has at least ten
candidates and no release shortfall.

**Decision gate:** resolved 2026-08-22. The verified retained OpenSubtitles bank
is the exclusive source for this audit; no silent fallback or source mixing.

**Exit:** all candidates have stable sentence/source IDs, target text, English
translation, license/provenance where available, surface occurrence evidence
and explicit per-card shortfalls.

### Phase 6 — First visible Spanish release without WSD

**Owner:** Codex. **Status:** release built, validated, locally activated and
audited through the real app shell 2026-08-22.

Select up to three examples per card using only source quality, translation,
easiness and diversity rules. Compose an inactive 200-card release whose
examples are explicitly unassigned but whose SpanishDict options remain
browsable. Wire the existing app to the Spanish active-release aliases.

This is the earliest point at which Josh sees a real clean Spanish deck. It
tests ordering, UI, provenance, source selection, release isolation and progress
aliases without pretending WSD is finished.

Release `es-speech-audit-200-unassigned-20260822` contains 200 cards, all 600
examples, and 2,352 browsable SpanishDict meanings. No WSD or fallback ran.

The app audit selected Spanish, opened and resumed Level 1 / Set 1 exactly,
cycled all three OpenSubtitles examples, opened Card Data, and opened the JSTA
flag flow without submitting a remote write. Dictionary-only menu percentages
are now treated as navigation weights rather than WSD evidence: the card says
`Unassigned` and never renders a synthetic `100%` confidence.

**Exit remaining:** exercise Review after real JSTA progress exists and verify
one deliberately submitted flag after the backend deployment is confirmed.

### Phase 7 — Typed Spanish enrichment layers

**Owner:** Codex, one layer at a time. **WSD remains independent.**

Migrate only approved product behavior, each as an optional typed layer with a
coverage/error report:

1. morphology and complete surface analyses;
2. clitic/elision lookup and display metadata;
3. conjugations and English production cues;
4. SpanishDict usage/construction presentation;
5. MWEs/expressions;
6. synonyms and antonyms;
7. cognates/English/loanword/proper-noun routing;
8. personalised example frames.

The app must render a valid card when any layer is absent. No enrichment may
change card identity, silently exclude a card, or write into the base inventory.

**Decision gate for each layer:** retain behavior, redesign behind a contract,
or deliberately cut it. Do not port a file merely because the old app reads it.

**Exit:** approved layers reproduce their intended user-visible behavior on the
200-card candidate, with missing/invalid data surfaced by validation.

### Phase 8 — External WSD attachment when the method is ready

**Owner:** Josh's WSD work produces the bundle; Codex validates/imports it.

Do not copy the current WSD implementation into Fluency Next during the earlier
phases. The chosen method emits the already-defined closed bundle containing:

- exact run, inventory, menu, candidate and sentence-bank hashes;
- one disposition per candidate occurrence;
- selected stable menu leaf or explicit abstention;
- prompt/method/model versions and run time;
- scores/features needed for audit, clearly separated from calibration claims.

The currently known-bad real-speech confidence bands are not migrated as
truth. A future v5, v6 or simpler method can produce the same bundle contract.
Importing a new bundle creates a new immutable assignment layer and release; it
does not mutate or dilute the unassigned release.

**Decision gate:** approve the exact prompt/method IDs and acceptance policy
after the separate WSD evaluation is settled.

**Exit:** assigned and unassigned examples are explicit; no example can inherit
an assignment from another run.

### Phase 9 — Assigned 200×3 deck audit

**Owner:** Codex builds; Josh audits in the app.

Compose a new inactive release from the same inventory, menus and selected
examples plus the approved WSD layer. Compare it with both the unassigned clean
release and the current live Spanish deck.

Audit:

- card order and surface coverage;
- selected examples and translations;
- headword/POS/sense display;
- clitic, morphology and optional enrichment behavior;
- exact release/run provenance and JSTA flags;
- old versus clean progress resolution;
- no old-run contamination or service-worker staleness.

**Exit:** Josh signs off on the vertical slice and all blocking discrepancies
are either fixed or explicitly deferred.

### Phase 10 — Full Spanish build

**Owner:** Josh runs expensive commands; Codex supplies and checks them.

Create a new full profile after the 200-card architecture is approved. Run the
full inventory, menu snapshot/build, OpenSubtitles harvest, selection, optional
enrichments and—when ready—WSD. Every long stage is resumable or cache-backed
and prints its exact output directory and content hashes.

No stage reads the 200-card outputs as a fallback. No full command runs until
its estimated time, disk and model cost are stated.

**Exit:** validated full inactive release, coverage/shortfall reports, exact
composition and reproducible commands.

### Phase 11 — Progress dry run and local activation

**Owner:** Codex audits; Josh approves any Sheet mutation.

Dry-run the complete legacy alias mapping against a fresh local pull of
Progress. Report mapped, ambiguous, retired and unmatched rows. Do not delete
old progress. Only after approval, write any required alias/canonical rows in an
idempotent operation with a local backup.

Activate the full Spanish release locally and test normal use as JST and audit
use as JSTA. French and Spanish releases remain independently selectable.

**Exit:** existing Spanish progress appears correctly, new progress persists,
resume is release-safe, and rollback requires only selecting the previous
release/app—not restoring deleted rows.

### Phase 12 — Cutover readiness, not automatic deployment

**Owner:** joint decision.

Before Fluency Next becomes live, verify Spanish/French parity, offline/cache
behavior, Sheets contracts, flags, release switching, local rollback and the
deferred Artist-mode boundary. The old repository remains available until the
new deployment has been independently tested.

No GitHub app, production activation, old-repo deletion or deprecation happens
as a side effect of completing the Spanish data migration.

## Approval gates in order

1. Retain/rebuild/reject ledger.
2. Canonical identity and legacy progress-alias strategy.
3. Spanish frequency source and normalization.
4. SpanishDict snapshot and conjugation/clitic lookup representation.
5. OpenSubtitles/Tatoeba source policy.
6. Optional enrichment layers, one at a time.
7. WSD bundle method IDs and acceptance policy, when ready.
8. 200×3 assigned candidate.
9. Full-run command and cost.
10. Progress write and local activation.
11. Eventual production cutover.

## Immediate next action

Codex implements the Spanish Speech rehearsal/audit profiles and explicit
language policies. The approved identity crosswalk is already validated. No
harvesting, WSD, large copying, Sheet mutation or release activation occurs in
the profile/configuration unit.
