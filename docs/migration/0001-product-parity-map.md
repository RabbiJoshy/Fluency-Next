# Fluency product parity map

- Status: exact app surface transplanted; clean data/release boundary active
- Reference application: `/Users/joshuathomasamar/PycharmProjects/Fluency`
- Reference URL: `http://127.0.0.1:4174/`
- Captured: 2026-08-20
- First rebuilt vertical slice: French Speech

## Product migration rule

The rebuild preserves Fluency's recognisable product, screen flow, study
behaviour, and mobile interaction model. It does not preserve implementation
coupling. A feature is removed only when the owner explicitly approves its
removal; otherwise it is either ported in the first vertical slice or retained
as a named later capability.

The old repository remains runnable and read-only during the rebuild.

## Reference journey captured

The existing application was exercised locally as a guest through this path:

1. Welcome surface.
2. Empty setup with top bar and `Choose language` step.
3. Radial language picker.
4. French selected in Speech mode.
5. French level and set selection.
6. A 20-card French study set.
7. Target-language card front.
8. Revealed card back with POS, sense, meaning, example, and lookup action.
9. Study-options sheet.
10. Study-preferences sheet.
11. Mobile card-back layout at 390 × 844.

Observed French reference data at capture time included 11,685 cards, level 1
ranks 1–198, ten sets, rank/frequency claims, and the legacy `Merge Lemmas`
control. Those numbers are evidence about the old release, not requirements for
the new French pipeline.

## Visual contract

The first rebuilt slice preserves:

- Near-black page background and dark blue-grey raised panels.
- Compact centred setup column.
- Numbered circular setup steps with the active language colour.
- Fluency's top utility bar and compact status/action controls.
- Radial language chooser with flags, centre label, backdrop blur, and
  unavailable-language treatment.
- Language source card with flag, language name, source label, and direct
  source-mode action.
- Level summary, horizontal level scrubber, numbered set selector, set-state
  legend, and primary start/review action.
- Study card with the existing fine gradient border, layered deck treatment,
  target headword scale, POS treatment, meaning rows, examples, and lookup
  placement.
- Desktop numbered scrubber and compact navigation.
- Mobile full-width study card, inline numbered/pip scrubber, and settings
  button.
- Existing typography families: DM Sans for body/UI, Space Grotesk for strong
  display/UI labels, and JetBrains Mono for ranks, labels, and percentages.
- Existing French colour treatment rather than introducing a new pilot theme.

## Behaviour contract: port in the French vertical slice

### Boot and setup

- Local guest entry without a remote dependency.
- Loading and recoverable error states.
- Top-bar help, local status, find, and settings positions.
- Language picker and selected-language summary.
- Speech as a registered mode, not a hardcoded default branch.
- Level and set selection from release-supplied grouping metadata.
- Pilot releases use the same controls with a clearly labelled Pilot level and
  no fabricated coverage/frequency claim.
- New, review, and unfinished/known state presentation.

### Study

- Target-first and English-first direction.
- Automatic and manual target-language speech.
- Card reveal/flip before scoring.
- Correct and incorrect scoring.
- Previous/next and direct-position navigation.
- Target headword, rank when supplied, POS, meanings, sense prominence when
  supplied, contexts, and examples.
- Multiple meanings and multiple examples.
- Per-card lookup links supplied by language configuration.
- Session progress and completion summary.
- Keyboard access for flip, answer, navigation, examples, and menu.
- Local session continuation and stable card-ID progress.
- Responsive desktop and mobile layouts.

### Preferences

- Exclude Cognates remains a capability; it is not silently removed.
- Spaced repetition remains a capability.
- Extra examples remains a capability.
- Phrases mode remains a capability.
- Card-front direction remains a preference.
- Automatic speech remains a preference.

Controls are shown only when the selected release/language declares the
required capability. The shared study engine does not contain Spanish- or
French-specific `if` branches for them.

## Explicitly remove

These removals have owner approval:

- Lemma cards as an alternate identity.
- `Merge Lemmas` in setup and preferences.
- Legacy surface/lemma progress branching.
- Any pipeline behaviour that copies lemma senses onto surface cards merely to
  preserve the old deck shape.

These remain cleanup targets after parity is locked. The exact transplant still
contains some of them internally, but the clean pipeline and release adapter do
not depend on them:

- Mutable state exposed through `globalThis`.
- Side-effect-only import ordering as application wiring.
- Runtime Gemini/WSD calls.
- Implicit reads from mutable `latest`, intermediate, or language data files.
- Implicit reuse of an older run when a new run lacks a record.
- Permanent version query strings on every module import during local R&D.
- Speech startup loading Artist, Spotify, cloud synchronization, or offline
  catalogue machinery.
- One monolithic card controller for every mode and language.

## Preserve as later capabilities, not Speech boot dependencies

The following remain part of the intended Fluency product but do not block the
first local French Speech slice:

- Initials authentication and cross-device progress.
- Durable cloud synchronization and offline operation.
- PWA installation and production service-worker caching.
- Vocabulary import/export.
- Card issue reporting and research feedback.
- Rich word-by-word sentence breakdown.
- Conjugation and morphology panels.
- Level estimation.
- Artist/Lyrics mode, artist picker, song selection, audio, and Spotify.
- Multi-artist and custom-song selection.

Their UI locations and data contracts must be preserved so adding them does not
require another shell rewrite.

## Release selection and anti-staleness contract

The app loads exactly one immutable release manifest. It never scans run
directories and never loads an individual layer by filename convention.

Every release locks each contributing layer to a run ID and content hash:

```text
inventory          -> run ID + artifact hash
sense menu         -> run ID + artifact hash
sentences          -> run ID + artifact hash
WSD assignments    -> run ID + artifact hash
example selection  -> run ID + artifact hash
manual overlays    -> run ID + artifact hash
```

Missing records remain missing unless a composition manifest explicitly names
a fallback run and policy. Composition defaults to conflict/error, never merge
or backfill.

The local application provides a development-only release selector and a
diagnostics view showing release ID, contributing runs, hashes, WSD method,
fallback counts, and candidate/approved status. Selecting a research run means
selecting or building a complete composition manifest; it does not mutate a
running release.

## Shared multilingual boundary

The core app receives language and mode information from registries. Adding a
normal Speech language should require configuration and a valid release, not a
copy of the application.

Language configuration owns:

- Name, flag, locale, and theme.
- Available modes.
- Release base path.
- Reference links.
- Optional capability modules.

Mode configuration owns:

- Setup source presentation.
- Release payload adapter.
- Mode-specific evidence and controls.

Stable surface card identity is shared across modes. Sense/example evidence and
release provenance remain mode- and release-specific. Cross-mode progress
sharing requires a later explicit product decision.

## Implemented app boundary

The standalone pilot UI was replaced by the real Fluency app surface. Its
existing module structure is intentionally retained during parity work:

```text
app/
├── index.html
├── css/
├── js/
├── config/
└── service-worker.js
```

The Python server maps the old split-data request paths to generated assets in
the active immutable release. No historical language-data tree is copied. A
later frontend refactor must preserve parity through tests and browser checks;
it is not mixed into the pipeline migration.

## Acceptance sequence for the first working version

1. Open local Fluency Next.
2. Enter locally as guest.
3. Open the same radial language picker.
4. Select French.
5. Remain in Speech and see the same setup hierarchy.
6. Choose the available 25-card fixture deck (20 cards in set 1, five in set 2).
7. Study in the recognisable Fluency card interface.
8. Reveal meanings and examples, hear French, score cards, and navigate.
9. Reload and retain local progress.
10. Independently validate the exact release manifest and contributing hashes.

No WSD completion is required for this sequence.
