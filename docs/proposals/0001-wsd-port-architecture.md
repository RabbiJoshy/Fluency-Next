# Proposal 0001: language-adapted closed-menu WSD

## Status

Approved after the Spanish WSD audit on 2026-08-22. The dependency-free
contracts and orchestration skeleton are implemented. No models, prototypes,
calibrators, historical assignments, or heavy ML dependencies have been copied
into Fluency Next; the French model profile remains explicitly blocked pending
the agreed benchmark.

## Authoritative Spanish reference

The current best Spanish Speech chain is not the older Gemini classifier. It is:

1. `step_6e_assign_senses_calibrated.py` (`spanishdict-beto-cal-v3`):
   cross-lingual gloss embeddings propose a leaf; a Spanish clitic gate may
   prune plain/reflexive analyses; gated BETO token prototypes may replace the
   winning `(headword, POS)` tuple; embeddings choose the leaf inside that
   tuple; a Spanish-trained calibrator estimates leaf correctness; defective
   empty/constraint-violating leaves are repaired inside the tuple; disposition
   may retain, reject, or send weak cases to a generative closed-set picker.
2. `step_6f_align_english_leaf.py` (`spanishdict-beto-cal-align-v4`): mBERT
   SimAlign binds the target surface to a word in the English parallel line and
   corrects a leaf where that aligned word matches a distinguishable gloss
   head. It writes only changed occurrences and does not overturn generative
   escalation claims.

The same current build also contains a newer downstream menu-binding correction
in `step_8a_assemble_vocabulary.py`. SpanishDict sometimes stores an attached-
clitic surface such as `dame` under its own surface headword even though legacy
routing names the card `dame|dar`. The assembler may use that surface analysis
only when a claim exists for that exact card key. This is not another WSD signal:
it preserves the menu on which an upstream decision was already made. It must
not be confused with the rejected loose `analyses[0]` fallback, which could give
one surface another headword's senses.

The current pinned Spanish Speech policy admits aligned corrections first,
then generative escalations, then local v3 claims. The checked-in Speech layer
contains local v3 and aligned-v4 evidence; no `sd-beto-cal-esc-v3` prompt stamp
is present, so the current Speech artifact did not use generative escalation.

## What is genuinely shared

- Closed-menu scoring: compare one sentence with every candidate sense.
- The distinction between a dictionary leaf and a `(headword, POS)` tuple.
- Restricting a leaf choice to a tuple selected by an independent token signal.
- Candidate score/gap calculation and explicit abstention/disposition.
- Token-vector and word-alignment cache semantics.
- Alignment as a sparse correction that abstains on ambiguous evidence.
- Exact model/config/input/output hashes and immutable run artifacts.
- Stable joins by `card_id`, `sentence_id`, and `sense_id`.
- An explicit, content-addressed binding from a surface card to the exact menu
  analysis WSD scored; the assembler consumes that binding instead of looking
  the menu up again heuristically.
- A complete decision trace rather than a single opaque method label.

## What must remain language- or provider-specific

- Sense-menu ingestion and provider metadata. SpanishDict `used with` notes,
  empty leaves, and headword conventions are not Wiktionary contracts.
- Surface/token location. Spanish conjugation, suffix stemming, accent handling,
  and clitic clusters cannot be used as French token rules.
- Morphology and clitic gates. The measured Spanish `se` gate has no authority
  over French reflexive/pronominal constructions.
- Contextual encoder and token prototypes. BETO and its checked-in prototypes
  are Spanish assets.
- Confidence calibration. The current model was trained on SpanishDict gold,
  Spanish menus, Spanish features, and the Spanish decision distribution.
- Provider-specific leaf repair. French Wiktionary constraints need their own
  parser and evidence before any hard gate is enabled.
- Evaluation panels and operating thresholds.

## Audit findings that should not be ported

1. The reference script hard-codes `Data/Spanish`, SpanishDict paths, BETO,
   Spanish regexes, and the Spanish calibrator.
2. It silently falls down to weaker variants when prototypes, a calibrator, an
   API key, or parallel text are absent. Fluency Next must instead name the
   exact variant in its profile and fail if a required component is missing.
3. It merges new methods into a mutable assignment file and relies on a global
   priority registry. That is the old-run dilution failure Fluency Next exists
   to remove.
4. It still uses numeric example positions before adding stable IDs. With
   rejection or `keep-best`, the current writer renumbers retained picks rather
   than writing their preserved original index, so a filtered run can stamp the
   wrong sentence. Fluency Next must never use a list position as assignment
   identity.
5. Confidence is path-dependent. The Spanish calibrator was trained on the
   gloss-prediction distribution, while BETO can replace that prediction; an
   alignment correction deliberately has no calibrated confidence because it
   chooses a different leaf. A final assignment must not inherit a score that
   was calibrated for another decision path or another sense.
6. Model names are not enough. Repository profiles must pin downloadable model
   revisions and API model identifiers; cached vectors must include those pins
   in their keys.
7. Heavy ML packages belong in an optional WSD dependency group, not the
   standard-library orchestration core.
8. The legacy assembler had to recover `dame`'s surface-headword menu because
   its card key still contained a lemma. Fluency Next uses surface-form card
   identity, but that alone is not enough: the normalized menu stage must give
   every candidate analysis an exact identifier and WSD must preserve the ID it
   selects. Assembly must fail
   visibly if that binding is absent or inconsistent; it must never choose the
   first analysis or silently search a different headword.

## Proposed repository structure

No folder below should be created until this proposal is approved.

```text
config/wsd/
├── shared/
│   └── closed-menu-v1.json       # stage order, abstention and trace contract
├── languages/
│   └── fr-v1.json                # token/morphology/provider adapters only
└── models/
    └── fr-rehearsal-v1.json      # exact revisions; initially unresolved

src/fluency/wsd/
├── __init__.py
├── config.py                     # exact shared/language/model profile loading
├── contracts.py                  # assignment and decision-trace validation
├── menus.py                      # provider-neutral leaf/tuple view
├── gloss_scoring.py              # sentence-to-leaf embedding scorer
├── token_prototypes.py           # shared prototype algorithm
├── calibration.py                # validates path-specific calibrator artifacts
├── alignment.py                  # parallel-English sparse corrector
├── disposition.py                # retain/reject/abstain policy
├── runner.py                     # immutable stage-04 execution
└── languages/
    ├── base.py                   # language adapter protocol
    └── french.py                 # French surface location and optional gates

schemas/
├── sense-menu.schema.json
├── wsd-assignment.schema.json
└── wsd-report.schema.json

tests/wsd/
├── test_contracts.py
├── test_gloss_scoring.py
├── test_token_prototypes.py
├── test_alignment.py
├── test_runner.py
└── test_french_adapter.py
```

Generated data remains outside the repository:

```text
<workspace>/runs/fr/speech/<run-id>/stages/04_wsd_assignments/output/
├── assignments.jsonl
├── report.json
└── manifest.json

<workspace>/objects/sha256/        # immutable model-derived artifacts
<workspace>/cache/models/          # downloaded model files
<workspace>/cache/derived/         # keyed vectors/alignments safe to regenerate
```

## Proposed assignment contract

One final record per `(card_id, sentence_id)`—never a mutable union of methods:

```json
{
  "assignment_version": "wsd-assignment/v1",
  "card_id": "card_fr_...",
  "surface_form": "...",
  "sentence_id": "sentence_...",
  "sense_menu_content_id": "sha256:...",
  "menu_analysis_id": "analysis_...",
  "status": "assigned",
  "selected_sense_id": "sense_...",
  "selected_tuple": {"headword": "...", "part_of_speech": "..."},
  "decision_path": ["gloss", "token_tuple_vote", "alignment"],
  "evidence": {},
  "confidence": null,
  "model_revisions": {}
}
```

`status` may be `assigned`, `abstained`, `rejected`, or `no_menu`. Evidence
stores each stage's candidates, scores, thresholds, aligned English words, and
reason for changing or abstaining. Confidence is present only when a calibrator
was trained for the final decision path and selected sense; otherwise it is
honestly `null`.

`menu_analysis_id` is the exact normalized analysis that supplied the candidate
leaves. The deck assembler must consume it unchanged. It may not repeat menu
resolution from a lemma, fall back to the first analysis, or substitute another
analysis whose headword merely looks related. This makes the current Spanish
surface-headword correction structural rather than a special downstream patch.

WSD assigns or abstains on harvested candidates. It does not select the final
three examples. `05_example_selection` makes that separate choice from the
complete WSD artifact.

## Proposed first French profile

- Wiktionary supplies `sense-menu/v1`; its headword is metadata, not card
  identity. The normalization stage resolves redirects/form-of information and
  emits explicit IDs for every candidate analysis before WSD; the chosen ID is
  carried by the assignment. Absence becomes `no_menu` rather than a downstream
  fallback.
- Gloss scoring, token prototypes, calibration, and aligned-English correction
  are separately switchable but never silently optional.
- No Spanish clitic gate, BETO artifact, Spanish calibrator, SpanishDict leaf
  repair, historical assignment, or global method priority is imported.
- No generative escalation in the first French audit. Harvest depth and explicit
  abstention keep the experiment interpretable; escalation can be evaluated as
  its own later profile.
- The French contextual encoder and final decision-path calibrator remain
  unselected until a French benchmark exists. Architecture and synthetic tests
  can be completed before those model choices.
- The multilingual alignment corrector is a candidate for reuse, not assumed
  valid merely because its model is multilingual. It needs a small frozen
  French panel before activation.

## Approved decisions

1. Use one immutable final assignment per card/sentence plus a full decision
   trace, replacing mutable method merging and priorities.
2. Use fail-closed component profiles: missing prototypes/calibrator/model
   pins cause an error rather than silent degradation.
3. Keep token models, prototypes, calibrators, morphology,
   and evaluation thresholds language-scoped.
4. Use no generative escalation in the first French audit.
5. Build the full skeleton before choosing or running the French
   encoder/calibrator benchmark.
