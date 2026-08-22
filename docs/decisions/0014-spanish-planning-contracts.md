# Decision 0014 — Spanish planning contracts

## Decision

Spanish Speech uses the same run and artifact families as French, with
language/provider behavior selected by configuration rather than a second
pipeline. Two profiles exist: a 20-card rehearsal and a 200-card audit, each
targeting three examples per surface.

The profiles are planning contracts only. They forbid lemma identity, legacy
inputs, implicit fallback and automatic release activation. Creating a plan
does not scan an inventory, read a corpus, assign a sense or build a release.

## Spanish boundaries

- `config/inventory/languages/es-v1.json` contains only reviewed Spanish
  exclusions; it does not choose the frequency source.
- `config/languages/es/tokenization.json` preserves accents and treats an
  observed attached-clitic form as its own surface card. Base forms are lookup
  candidates only.
- `config/harvest/languages/es-v1.json` supplies Spanish normalization and
  token-boundary behavior to the shared harvester. OpenSubtitles is selected
  exclusively for this audit; another source must be an explicit new profile.
- `config/sense_menu/languages/es-spanishdict-v1.json` binds SpanishDict menus
  to surface-card identity while preserving returned headwords, conjugator and
  clitic analyses as lookup metadata. Fuzzy corrections are quarantined.
- `config/wsd/languages/es-v1.json` owns Spanish POS, `se`-clitic and
  renderable-leaf behavior.
- `config/wsd/models/es-sd-beto-cal-v5-migration-v1.json` records the current
  audited method and assets without importing assignments or claiming that the
  assets already exist in Fluency Next.

## Deliberate blockers

The inventory source edition and measure remain
`pending-explicit-source-approval`. The old `SpanishRawWiki.csv` filename is
not sufficient provenance for an authoritative ranking source.

WSD remains `blocked_pending_assets` until the exact Gemini cache, BETO runtime
assets and legacy calibrator are migrated with content-addressed manifests.
The base profile keeps Gemini escalation and aligned-English correction
disabled; both remain separately versioned optional methods. The calibrator is
retained for reproduction but cannot drive Speech release rejection because it
was not validated on real speech.

## Verification

All 139 repository tests pass. Both Spanish profiles validate through the
runtime planner, and a temporary 20×3 plan created six pending stage contracts
without executing data work or activating a release.
