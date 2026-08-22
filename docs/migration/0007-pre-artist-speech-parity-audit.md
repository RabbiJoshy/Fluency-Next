# Pre-Artist Speech parity audit

## Decision

The clean app and Speech architecture are ready for Artist-mode migration.
WSD, the full Spanish build, final progress migration and deferred linguistic
enrichments remain later Speech/cutover work; none is an Artist prerequisite.

## Verified behavior

The 2026-08-22 browser audit used the real transplanted app and active local
French and Spanish releases. It verified:

- JSTA can resume an unfinished release-owned Speech set;
- Spanish renders three retained OpenSubtitles examples with explicit
  `Unassigned` sense status;
- Card Data exposes all three examples and their source names without requiring
  a WSD assignment;
- French renders three retained Tatoeba examples from its independent release;
- switching Spanish to French and back does not mix cards, examples, menus or
  optional language data;
- release-driven levels, the active-set interaction model and audit controls
  survive the switch.

No flag, progress or other remote write was submitted during this audit.

## Bug fixed at the gate

The transplanted app kept its active examples split in one global cache. After
one language loaded examples, another language could reuse that object and find
none of its own card IDs. The release data itself was correct; the active cache
pointer was not source-aware.

The app now records the examples source path, reloads when the configured path
changes, and clears example plus optional conjugation/cue state at the language
boundary. This is also the required behavior for future Dutch and Portuguese
Speech releases and for entering/leaving language-specific Artist catalogues.

## Deliberately deferred

English production cues are not a stand-alone pre-Artist layer. Their renderer
needs per-card morphology to choose person, mood and tense, while the clean
Spanish audit release intentionally contains no morphology rows. The old derived
cue table and its inflection dependency remain excluded until morphology is
approved as a bounded optional layer.

The following also remain outside the Artist start gate:

- external WSD attachment and assigned 200-card audit;
- the full Spanish inventory/release build;
- Sheet progress alias mutation and production cutover;
- MWEs, lexical relations, cognates and personalised frames.
