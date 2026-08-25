# Spanish speech WSD v7: frozen architecture and runbook

v7 is a conservative production foundation for further NLP research.  It fixes
the speech execution bugs exposed during the v6 audit, retains counterfactual
decisions that were previously discarded, and gives optional specialists a
provider-neutral interface.  It does **not** enable an unvalidated new signal.

## The four decisions v7 keeps separate

1. **Candidate universe**
   - `provider_only` is the active default.
   - `mwe_augmented` is scored in the same pass and stored whenever an expression
     is present.  It cannot silently replace the provider answer.
2. **Exact classification**
   - Every evaluated occurrence retains an exact forced leaf.
3. **Supported publication**
   - `emitted_level` is independently `leaf`, `glosskey`, `tuple`, or
     `unresolved`.  Raw score margins are not described as calibrated confidence.
4. **Release view**
   - Candidate universe and publication specificity are selected when building
     a release.  Switching either view never reruns WSD or embeddings.

Legacy assignment fields remain the active forced decision.  The optional
`selection_projections` object carries both candidate universes, and
`active_selection_projection` says which one the legacy fields materialize.

## Fixed contradictions

- Speech v6 accepted `observed_pos` but never computed or passed it.  v7 tags
  exact speech occurrences with pinned `es_dep_news_trf@3.8.0`, at batch size 1,
  and explicitly reports repeated-occurrence disagreement.
- POS and `se` rules again constrain the published provider decision, matching
  the reliable v6 ordering.  Rejected analysis IDs remain typed audit evidence.
  The policy falls back to the complete provider set if a gate would erase it,
  so a tag mismatch cannot create a no-candidate result.
- Provider PHRASE rows are not treated as synthetic MWE candidates.  MWEs join
  only after the provider constraint stage; this prevents single-form English
  renderings such as `está -> he's` from bypassing the verb gate.
- Exact elisions retain their raw persisted span for assignment, while the POS
  model sees the canonical restored target (`'toy -> estoy`).  AUX occurrences
  also suppress the misleading lexical-reflexive reading in constructions such
  as `se ha ido`.
- `MenuAnalysis.to_dict()` now retains `source_adapter`; reconstruction no
  longer defaults every language to SpanishDict.
- App frequencies can use all Stage-04 outcomes.  The denominator includes
  capped, rejected, no-menu and unsupported occurrences; known leaf mass is
  never renormalized to 100%.

## Portable specialist seam

Sense-menu adapters normalize only explicit evidence into typed features:

- SpanishDict: bare domain/register clauses, construction notes, and regions.
- Wiktionary/Kaikki: topics and mapped semantic tags; morphology/form-of tags are
  excluded.

Specialists see canonical leaf IDs, POS and normalized features, never raw
provider metadata.  Their result is `support`, `reject`, or `unknown`; a missing
feature means `unknown`, never rejection.  Representation channels are
`full_gloss`, `domain`, `register`, and `construction`.  Sparse channel texts are
deduplicated globally.  The specialist runner is evidence-only and disabled in
`es-v7-1` until a measured policy earns activation.

## Pinned profiles

- language: `config/wsd/languages/es-v2.json`
- model: `config/wsd/models/es-v7-1.json`
- 500-surface rehearsal: `config/pipelines/es/speech/v7-500x3.json`
- 2,000-surface build: `config/pipelines/es/speech/v7-2000x3.json`

COMMIT thresholds remain zero by default, so supported publication remains at
leaf level until calibration is measured.  Raw axis margins are retained for
that experiment but are not confidence values.

## Runbook

```bash
W=../Fluency-Workspace
PROFILE=config/pipelines/es/speech/v7-500x3.json

PYTHONPATH=src python3 -m fluency.cli pipeline plan --workspace $W --profile $PROFILE
# Use the printed RUN id for the remaining commands.
PYTHONPATH=src python3 -m fluency.cli pipeline inventory --workspace $W --run-id $RUN --language es --mode speech \
  --snapshot $W/raw/frequency/fluency-2026-07-28-surface-ranking-v1 --snapshot-id fluency-2026-07-28-surface-ranking-v1
PYTHONPATH=src python3 -m fluency.cli pipeline sense-menu --workspace $W --run-id $RUN --language es --mode speech \
  --snapshot $W/raw/dictionaries/es/spanishdict/spanishdict-complete-menu-2026-08-23-v1 --snapshot-id spanishdict-complete-menu-2026-08-23-v1
PYTHONPATH=src python3 -m fluency.cli pipeline harvest --workspace $W --run-id $RUN --language es --mode speech \
  --source retained-opensubtitles=$W/raw/opensubtitles-retained/retained-opensubtitles-2026-08-15-harvest-v1

PYTHONPATH=src python3 -m fluency.speech.wsd_execute --run-dir $W/runs/es/speech/$RUN \
  --out $W/raw/wsd/es-v7-$RUN/bundle.json \
  --profile-id es-v7-1 \
  --multiword-inventory $W/raw/mwe/mwe-merged-2026-08-23-v1/mwe_merged.json \
  --execution-cap 5
PYTHONPATH=src python3 -m fluency.cli pipeline wsd-import --workspace $W --run-id $RUN --language es --mode speech \
  --bundle $W/raw/wsd/es-v7-$RUN/bundle.json
```

The default live-compatible release is forced provider leaf:

```bash
PYTHONPATH=src python3 -m fluency.cli pipeline build-run-release --workspace $W --run-id $RUN \
  --release-id $RELEASE --language es --mode speech \
  --wsd-selection-projection provider_only --wsd-publication-projection forced_leaf
```

The conservative view uses the same Stage-04 assignments:

```bash
PYTHONPATH=src python3 -m fluency.cli pipeline build-run-release --workspace $W --run-id $RUN \
  --release-id $SUPPORTED_RELEASE --language es --mode speech \
  --wsd-selection-projection provider_only --wsd-publication-projection supported_specificity
```

To audit MWE impact, select `mwe_augmented` with a new release ID.  No model is
called in either release switch.

## Artist and cross-language migration status

The release contract is now generic across modes and languages. Native Speech
runs retain the forced leaf and an independently recorded supported level.
Materialized Artist sources are bridged into the same shape: their historical
leaf is retained as `forced_selection`, while unavailable support evidence is
explicitly `not_recorded` and is never inferred from the old leaf choice.

Artist releases package an artist-specific master and `wsdEvidencePath`, so two
artists may use different historical menus for the same stable card ID. The app
defaults to `forced_leaf`; `?wsdPublication=supported_specificity` selects the
conservative percentages without rerunning WSD. The same switch is exposed as
`window.setWsdPublicationProjection(...)` for a settings control.

## Post-v7 research: a missing publication rung

This is a measured follow-up, not a v7 blocker or an enabled policy.  On 3,059
polysemous SpanishDict entries, average candidates fall from 5.76 leaves to 5.01
glosskeys, but then to 1.19 tuples.  The small glosskey reduction (13%) matches
its small measured accuracy gain, 53.09% to 56.70%.  In practice the present
specificity ladder is close to leaf-or-tuple, with little useful middle.

A menu-derived group may fill that gap without adding another per-occurrence
signal.  Grouping the measured menu by `(pos, context)` produced 3.60 candidates
per entry.  Before that number can support implementation it must be recomputed
with two safety guards:

- the key must include `headword` as well as POS and context; different lemmas
  must never collapse into one publishable answer;
- empty, generic or otherwise non-discriminating contexts must not form a group
  merely because their strings match.

The resulting object should be called a menu-derived or contextual group until
an audit shows that it is genuinely semantic.  It may be computed offline and
stored as stable menu metadata.  It must not replace or merge the forced leaf:
it is an additional publication projection for one occurrence.  This preserves
the established finding that whether two leaves are interchangeable can depend
on the sentence.

Backoff also needs typed causes.  The working causes are
`model_uncertain`, `occurrence_underdetermined`, and `inventory_artifact`, plus
`unclassified` until evidence can distinguish them.  They should not initially
be assumed mutually exclusive: model failure, insufficient context and an
over-fine inventory can coexist.  Raw margins alone cannot assign these causes.

The intended consumer policies differ:

- a validated `inventory_artifact` group may publish confidently as a group;
- in speech mode, an `occurrence_underdetermined` example may be replaced when
  the card has enough alternatives, but the occurrence remains in the
  prominence denominator;
- artist mode cannot assume a replacement exists, so it must retain the
  occurrence or publish a coarser supported result rather than silently drop it;
- `model_uncertain` identifies the portion that better classification may
  actually improve.

WordNet supersenses are not the proposed implementation: their noun/verb-only
coverage and the measured weakness of naive gloss-to-supersense mapping on real
Wiktionary data make them a poor fit here.

## Verification and completion gate

The implementation passes all 297 repository tests (2026-08-24).

### Rosalía structural stress — corrected

The first `rosalia-v7-stress/v1` run incorrectly treated each example row as one
occurrence and tried to rediscover its canonical surface in raw lyrics.  That
discarded the artist pipeline's persisted occurrence spans and produced 370
false `surface_not_located` abstentions on restored elisions such as
`pa' -> para`.  Its completion claim and counts are superseded.

`rosalia-v7-stress/v2-persisted-occurrences` consumes the active evidence
profile's ledger spans directly and makes one decision per occurrence.  It
exercised 1,591 multi-sense SpanishDict surfaces and 3,846 persisted
occurrences from the first ten example rows per surface.  The active projection
was `provider_only`; `mwe_augmented` remained the counterfactual.  All 3,846
assignments survived schema round-trip.

- 3,846 assignments and zero location abstentions
- POS/clitic evidence fired on 661 occurrences and changed the diagnostic winner
  on 198
- 449 occurrences had an MWE candidate; the alternate projection changed the
  winner on 208
- inputs were pinned to menu content ID
  `sha256:dd7afa6d637ec14aef201814492994765639c4fa60309758dd75130aace80254`,
  MWE content ID
  `sha256:11b1c0ac83203871ed4f539abccf73f8bc722d22abf611a478a73d75fdb6579c`,
  and POS model `es_dep_news_trf@3.8.0`

This proves that Rosalía's menus, persisted occurrences, POS evidence, dual
candidate universes and assignment contracts run at library scale.  It makes no
accuracy claim.

### Rosalía production-scoring stress — corrected

After explicit approval, the 4,226 exact-text cache misses (1,724 sentence texts
and 2,502 dictionary-gloss texts) were embedded with `gemini-embedding-001` into
a disposable local delta.  The corrected occurrence-level run reused the
complete 6,787-text cache without another provider call.  No text was missing
and no score was non-finite.

- 3,846 assignments and zero surface-location abstentions
- POS/clitic evidence fired on 661 occurrences and changed the diagnostic
  constraint-aware winner on 198
- 449 occurrences had an MWE candidate; `mwe_augmented` differed from the active
  `provider_only` answer on 208
- provider-only matched 2,276 of 3,769 comparable retained assignments (60.39%)

The last figure is a regression comparator, not an accuracy estimate: retained
artist assignments are not audited gold.

### Rosalía classification audit — preview rejected

The corrected engineering run exposed three reasons the local preview is not a
quality candidate:

- The additive `0.02` menu-order prior changed the raw embedding winner on 1,134
  of 3,846 occurrences.  It moved 1,119 toward an earlier serialized leaf and
  landed 1,034 on leaf 1.  The final answer was leaf 1 on 71.0% of occurrences.
- The retained artist menu is not a pure provider inventory: 872 of 8,201 leaves
  use `generated:artist-master:*` IDs while claiming the SpanishDict source, and
  they won 240 decisions.  Clear failures include the generated noun `ha`
  beating auxiliary `haber` in compound tenses.
- Exact sentence-to-gloss cosine has weak separating power for close leaves:
  50.5% of raw top-two margins were below `0.01`, and 73.6% were below `0.02`.
  Eighty-four surface menus contain exactly identical rendered glosses, making
  221 evaluated occurrences mathematically inseparable by this representation.
  The scorer embeds the unmarked whole sentence and does not encode the target
  span.  Optional specialists were deliberately disabled, so they did not
  repair these cases.

The dual projections and typed diagnostic evidence made these failures visible,
but they do not make the active classifications acceptable.  A replacement
policy must keep structural evidence, contextual scoring and corpus frequency
as ordered decisions rather than adding the frequency prior to every score;
generated fallback leaves must also be separated from the provider universe.

### Rosalía production deck — clean v6 baseline restored

The rejected preview mixed the old artist menu with v7 scoring.  The replacement
uses the pinned speech snapshot
`spanishdict-complete-menu-2026-08-23-v1`, exact persisted occurrence spans, and
active v6-style POS/clitic constraints.  The published answer remains
`provider_only`; the `mwe_augmented` counterfactual is retained separately.

After explicit approval, the complete clean-menu stress scope was run: 2,505
polysemous surfaces and 5,250 exact lyric occurrences.  The 4,119 cache misses
(205 sentence texts and 3,914 dictionary-gloss texts) were embedded with
`gemini-embedding-001` into a disposable local delta.  Every occurrence was
assigned, with zero abstentions, schema failures, missing texts or non-finite
scores.  The provider constraint fired on 3,076 occurrences.  An MWE candidate
was available on 515 occurrences and changed the counterfactual winner on 231.

The clean menu has no `generated:artist-master:*` winners.  Audited regressions
now behave as grammar requires: `está`/`estoy` select VERB analyses, restored
`ta`/`'toy` receive canonical POS evidence, and `ha` selects non-reflexive
`haber` rather than the lexical `haberse` sense.  The ordinary `rosalia` deck
contains 3,224 cards and was rebuilt from these assignments.  All 3,215 prior
card IDs remain present, nine cards were added, and the retired preview artist
entry was removed.  Rosalía uses a run-matched dedicated master so its v7 sense
positions cannot be joined against the older shared Spanish master.

The engineering stress is complete, but semantic quality is not certified.
The menu prior changed the raw constrained embedding winner on 1,923 of 5,250
occurrences (36.63%), and the final answer was the first serialized leaf on
3,391 occurrences (64.59%).  Those figures are not proof that each such answer
is wrong, but they show enough menu-order influence that v7 must not claim final
leaf-level accuracy without a focused ablation and audit.
