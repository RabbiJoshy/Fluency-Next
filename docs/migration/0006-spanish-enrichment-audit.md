# Spanish Speech enrichment audit

## Decision

Spanish enrichments remain optional release layers. None may be read from the
old repository at runtime, change surface-card identity, exclude a card, or
silently supply missing WSD. The active 200-card release remains valid without
any enrichment layer.

This audit measured the old derived files against the 200-card candidate. It
did not copy enrichment data or create a new release.

## Measured coverage

| Old layer | Old size | Candidate coverage | Decision |
|---|---:|---:|---|
| `morphology.json` | 90.8 MB | 68/200 surfaces | Rebuild a bounded typed layer; do not copy the global derived table. |
| `clitic_forms.json` | 2.3 MB | ID-keyed | Reject as an input: 524/544 rows contain historical WSD assignments. Rebuild clitic analysis from surface morphology. |
| `conjugations.json` | 1.8 MB | 38/211 menu headwords | Rebuild from the pinned conjugation source as an optional headword layer. |
| `senses_conjugated_english.json` | 5.8 MB | 55/211 menu headwords | Regenerate production cues from the selected menu plus conjugation layer. |
| `mwe_phrases.json` | 320 KB | 77/200 surfaces | Defer; later preserve provider evidence and rematch expressions against release examples. |
| `synonyms.json` | 12.2 MB | 145/200 surfaces | Defer from the migration critical path; later validate as typed lexical relations. |
| `cognates.json` | 472 KB | 103/200 surfaces | Defer; rebuild with source/model provenance before restoring filtering. |
| `english_loanwords.json` | 149 KB | 0/200 surfaces | Defer until the full inventory; it cannot affect this audit deck. |
| `personalised_example_frames.json` | 29 KB | 18/200 target words | Defer; records depend on old card/sense IDs and require a clean identity remap. |

The SpanishDict construction/usage fields are already provider evidence in the
clean sense menu. They are not duplicated as a separate enrichment.

## Implementation order

1. Define a shared optional-layer envelope and validation behavior.
2. Rebuild bounded morphology and clitic analyses for the candidate cards.
3. Rebuild conjugations and English production cues from pinned sources.
4. Re-compose the same candidate release with only those explicitly selected
   layers and verify that removing any one still yields a usable card.
5. Consider expressions, lexical relations, cognates/routing and personalised
   frames independently; none blocks Spanish Speech migration or WSD import.

## Conjugation implementation result

The first clean optional layer was built from the pinned reconstructed Jehle
CSV, not from the old `conjugations.json` or `verbecc`. The source snapshot has
content ID `sha256:239d01e65b4e6d76509c8bb8abb6d2bc6792183d275270fd077f616d91132629`.

Artifact `sha256:ac8df2688d427ac98b1b173c2d7d797e3cdc298d737bb4457afc91d2fb06a4ed`
contains 30 requested headwords and 540 mood/tense paradigms. The candidate
menu requested 60 verb/AUX headwords, so 30 missing headwords remain explicit.
No fallback source was consulted. The layer joins by dictionary headword and
therefore cannot alter the 200 surface-card identities.

Release `es-speech-audit-200-unassigned-jehle-20260822` explicitly selects this
artifact and publishes the compatible app table through the stable
`Data/Spanish/conjugations.json` alias. The release retains the same 200 cards
and 600 explicitly unassigned examples, so attaching conjugations introduced no
WSD or example-selection drift. Browser verification rendered the complete
present-indicative row for `tener` in the existing card interface. For
surface-only cards the UI uses the current dictionary headword as the lookup
key; that lookup metadata never replaces the card's surface identity.

## Runtime cleanup

The app config no longer advertises old mutable files for conjugated English
cues or the misleading `SpanishRawWiki.csv`. Conjugations now use only the
stable release alias backed by the active release composition. If a release
omits that optional asset—or the requested headword is uncovered—the existing
app degradation paths remain authoritative and no legacy file is consulted.
