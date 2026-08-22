# Decision 0013: prediction-blind French WSD benchmark

## Status

Accepted and implemented on 2026-08-22. Gold annotation is pending.

## Why a French benchmark is required

The current Spanish Speech method is not one interchangeable model. Its shared
decision shape is portable: gloss embeddings propose a leaf, a language token
model may decide the headword/POS tuple, confidence controls disposition, and
aligned English may sparsely correct a leaf. Its learned evidence is not
portable: BETO prototypes, the Spanish feature calibrator, the measured 0.02
tuple margin, and the Spanish `se` clitic gate are Spanish results.

The newest Spanish surface-menu fix is preserved structurally, not copied as a
special French rule. A surface such as Spanish `dame` may retain its own
dictionary analysis when an exact claim selects it. Fluency Next already keys
French cards, candidate menus and assignments by surface-card identity and exact
menu analysis ID, so a redirected headword never erases a direct surface entry.

French therefore receives the same orchestration and evidence contracts, while
French token voting, morphology/clitic behavior, calibration and Wiktionary
leaf constraints remain disabled until measured on frozen French gold.

## Frozen selection

Run `20260822T172017Z-651bcd8e` contributes exactly 120 unique surface cards and
120 real Tatoeba French-English pairs:

- 40 rank-1-to-60 function-word or homograph cards;
- 40 lower-ranked redirected, inflected or multi-headword cards;
- 40 lower-ranked direct-headword, multi-sense lexical cards.

Every eligible card must have at least two menu leaves. Card selection and the
one candidate chosen for each card are SHA-256 ranked under
`fr-stratified-120/v1`; easiness order and future Python iteration order cannot
change the sample. The benchmark pins the exact inventory, menu, candidate and
sentence-bank hashes.

## Gold contract

The review file contains no model prediction, score, confidence or suggested
answer. A label binds to `benchmark_row_id` and records one of:

- an exact `(menu_analysis_id, sense_id)`;
- `no_listed_sense`;
- `bad_pair`;
- `unsure`.

Notes are optional. Browser progress is local to the exact benchmark content ID
and can be exported or imported as `wsd-gold-labels/v1`. Predictions are run
only after the gold export is frozen.
