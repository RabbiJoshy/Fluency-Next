# Spanish Speech WSD: v6 implementation map

Written before touching code, per the order of work. This says what changes, what
stays, which deterministic assets are imported versus recomputed, and which
schema changes are needed. Nothing here is implemented yet.

The method being ported was developed in the old repository and is recorded there
in `docs/reference/wsd_design.md` (philosophy and measurements) and
`pipeline/util_6g_v6.py` (reference implementation, defaults-off).

---

## What the audit found

**Fluency-Next's WSD layer is already well-shaped for this.** The
dependency-injected seams — `CandidatePolicy`, `GlossScorer`,
`TokenPrototypeReranker`, `AlignmentCorrector`, `Calibrator`,
`DispositionPolicy` — are exactly the "replaceable transformation" the goal asks
for. `wsd-request/v2` already carries typed eligibility, `menu_reference.analysis_ids`
(so requirement 3, explicit headword/POS analysis, is already satisfied), a
translation/alignment slot, and content-hash lineage.

**But its decision order is v5's.** `DECISION_ORDER = (gloss, token_tuple_vote,
leaf_repair, calibration, alignment)` is the seven-stage pile that v6 reorganises.

**It inherited the AUX bug.** `wsd/languages/spanish.py: POS_BRIDGE` holds
`DET, PRON, NUM, PART, PROPN, ADV` and no `AUX`. SpanishDict has no AUX category
and files every auxiliary and modal as VERB, while the tagger emits AUX — so for
`haber, ser, estar, deber, saber` the filter rejects every analysis, the
empty-set fallback fires, and the stage is a silent no-op on the commonest verbs
in speech. Fixed in the old repository; must be fixed here too.

**One real difference to be careful about.** `SpanishV5CandidatePolicy.prepare`
filters whole **analyses**; the old implementation filtered **leaves**. These are
not equivalent when one analysis mixes parts of speech. Behaviour must be pinned
by test either way, not assumed.

---

## The change: three roles, not seven stages

Every existing component keeps its seam and gains a role. This is a
reorganisation, not a rewrite:

| role | job | existing component |
|---|---|---|
| **CONSTRAIN** | remove candidates that cannot be right | `CandidatePolicy.prepare` |
| **RANK** | one score over survivors | `GlossScorer` + `adjust_scores` |
| **COMMIT** | decide *how specific* an answer to emit | replaces `Calibrator` + `DispositionPolicy` |

**COMMIT is the only new idea.** A system that must always emit a leaf turns
every uncertainty into a wrong card. One that can emit a leaf, a glosskey (gloss
without context) or a tuple (headword+POS) turns uncertainty into a *less
specific* card. Escalation triggers on the **tuple** axis alone: being torn
between two synonyms is not worth an API call, because the learner never sees the
difference once the answer is emitted at glosskey level; being unsure which word
this is always is.

Three dispositions exist for an uncertain pick and they aim at different axes —
this matters because picking the wrong one does nothing:

    gloss uncertain  ->  emit less        (rejection does not help; leaf accuracy
                                           is flat across the whole rejection curve)
    tuple uncertain  ->  reject & redraw  (speech: the corpus is 61M lines and a
                                           card needs three examples)
                     ->  escalate         (lyrics: a fixed user corpus cannot redraw)

---

## Deterministic assets: import or recompute

| asset | decision | why |
|---|---|---|
| **Gloss/menu embeddings** | **recompute** | The old cache holds 276,724 vectors at 97.3% coverage, but its manifest claims 17,861 vectors over "839 words, PARTIAL". Manifest and asset disagree, so provenance cannot be reconstructed honestly. The input text also depends on menu construction, which differs here. Recomputing ~95k texts is ~1.4M tokens, about **$0.21** — verification would cost more than recomputation. |
| **Sentence/context embeddings** | **recompute** | Per-run and per-corpus by definition. A fresh run has fresh sentences. |
| **BETO token prototypes** | **do not port at all** | Measured below the baseline (75.4% vs 78.4%), and the depth curve shows they need 13+ labelled examples per sense while the deck median is 4. Dropping them deletes a 45MB asset, a torch dependency and a decision stage. This is an algorithmic improvement, not a migration decision. |
| **MWE phrase caches** (SpanishDict `phrases_cache.json`, Wiktionary `mwe_phrases.json`) | **import as pinned raw inputs** | Scraped source data, not decisions. Hash and pin them. |
| **MWE merged inventory** | **port the tool, regenerate** | Derived by a deterministic scan of OpenSubtitles with no model. Regenerating is ~3 minutes and yields its own provenance. |
| **Any sense assignment, selected example, deck, override** | **never** | Clean data boundary. |

---

## Schema changes needed

Four, three of them additive.

**1. `DECISION_STAGES` / `DECISION_ORDER`** — add the v6 role names. Additive; the
frozenset currently rejects anything outside the v5 stage names.

**2. Emit granularity on the result.** New field, e.g.
`emitted_level: "leaf" | "glosskey" | "tuple"`. Without it a glosskey-level
answer is indistinguishable from a leaf answer that happens to have a null
context, and COMMIT becomes unauditable.

**3. Decision kind.** `decision_kind: "deterministic_default" | "disambiguated"`.
Requirements 5 and 10 need this and there is currently nothing for it in the
Python contract — the auditor's automatic/genuine distinction was added app-side
only.

**4. MWE, which needs a design decision — flagging rather than assuming.**

Multiword senses compete as ordinary candidates. Measured on 29 panel items
carrying one, the multiword sense beat every leaf on 15; hand-graded 12 good, 5
compositional false positives. The good ones include `a menos que` = unless
(previously "minus sign"), `por qué` = why (previously "by"), `sitio web`,
`da igual`, `en todas partes`.

They compete rather than veto deliberately: only 9% of MWE hits map cleanly onto
an existing leaf, and about a quarter are compositional strings like `no tiene`
where a veto would delete the correct answer. Competing, a junk entry costs one
mediocre card meaning; vetoing, it costs a correct one.

**Proposal.** The request stays single-surface — an MWE offers a candidate to
each component surface, and lands on whichever card that occurrence was selected
as evidence for. Card identity is untouched. The result gains an optional block:

```json
"mwe": {
  "expression": "de nuevo",
  "expression_id": "mwe_bbb",
  "span": [18, 26],
  "corpus_freq": 9900,
  "component_surface_forms": ["nuevo"],
  "inventory_content_id": "sha256:..."
}
```

This satisfies "represent the expression, component occurrences, spans, routing
and assignment relationship explicitly" without hiding anything in a string
correction, and without a second identity system.

**Two tiers must not be collapsed.** An MWE with `corpus_freq > 0` has sentences
behind it and can be assigned to an occurrence. One with `corpus_freq == 0` is
teachable content with no sentence to attach — it can never be an occurrence
outcome and must never be offered as a candidate.

---

## Order

1. Fix the AUX bridge and pin it by test. Independent of everything else.
2. Schema changes 1–3, with tests.
3. MWE tier-1 candidates behind a profile flag, defaulted off.
4. Restructure the runner into the three roles, defaults reproducing current
   behaviour pick-for-pick.
5. Recompute the gloss embedding snapshot, typed and provenance-bound.
6. Small Spanish fixture through the real contracts; inspect every outcome.
7. Bounded Spanish Speech run, release left inactive.

Steps 1–4 change no output until a profile turns something on, which keeps the
French and Bad Bunny demonstrations safe throughout.

---

## What is deliberately not carried over

- The confidence calibrator. It was trained on dictionary gold and applied to
  real speech, so 58% of the old deck read "low" and the bands were meaningless.
  COMMIT's margins replace it.
- Leaf repair as a stage. It becomes a case of COMMIT — an empty gloss is a leaf
  you cannot defend, so emit the glosskey instead.
- The token-prototype tuple vote, per the asset table above.
- Domain-weighted ranking. Domain matching in isolation scores 92.6% against a
  43% prior, but adding it on top of the existing score is flat then negative:
  the baseline is already 90.9% on the items where domains compete. Recorded so
  nobody re-derives it.
