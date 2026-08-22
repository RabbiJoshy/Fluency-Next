# Spanish Speech source and component ledger

## Purpose

This ledger is the first approval gate in the Spanish Speech migration. It
classifies the mature Spanish repository by value, not by age or by whether a
file happens to be read by the current application. The clean migration keeps
irreplaceable source evidence and paid computation, ports the current WSD
method as a versioned implementation, and rebuilds disposable decisions and
application outputs.

The source repository was audited at commit
`23f1ad4387feb4a599815eaa6846e1201b5f402a`. No old data was copied and no
assignment or release was activated while producing this ledger.

## Approved migration policy

### Retain exactly

- harvested sentences, translations, stable sentence IDs and source
  provenance;
- the surface-to-sentence occurrence/candidate mapping produced by harvesting;
- every paid Gemini embedding and its exact-text index;
- pinned source evidence needed to rebuild menus or lookup analyses;
- learner progress aliases and the evidence needed to map them;
- executable assets required to reproduce the current WSD method, clearly
  separated from its assignment outputs.

### Rebuild from retained sources

- all WSD assignments and assignment-derived sense shares;
- final three-example selection;
- confidence bands and acceptance decisions;
- compact app indexes, example files, deck ordering and releases;
- coverage reports and all mutable `active` pointers.

### Leave behind

- historical assignment generations and their unions;
- legacy Gemini classification outputs;
- lemma-indexed assignment layers;
- stale orchestration and scripts that write directly into mutable `Data/`;
- duplicate snapshots, pre-migration deck copies and one-off intermediates;
- implicit fallbacks, old-method priority resolution and builder behavior that
  admits several assignment generations at once.

### Provenance rule

Missing provenance is never invented as fact. A recovered asset receives a
manifest with one of these statuses:

- `observed`: directly supported by the source artifact or its manifest;
- `reconstructed`: inferred from named files, code, commits or content, with
  the inference basis recorded;
- `unknown`: not recoverable; the missing field remains explicitly unknown.

Every retained asset must have a content hash. Reconstructed manifests also
record the old absolute/relative path, audit commit, recovery date and the
evidence supporting each inferred field.

## Cross-language standard

Spanish must use the same artifact families as French and future languages.
Only tokenization, lookup generation, menu-provider interpretation and other
genuinely linguistic behavior may live in a language adapter.

```text
Fluency-Workspace/raw/
  inventories/<language>/<provider>/<snapshot-id>/
  menus/<language>/<provider>/<snapshot-id>/
  corpora/<language-pair>/<provider>/<snapshot-id>/
  sentence_banks/<language>/<provider>/<snapshot-id>/
  embeddings/<provider>/<model>/<snapshot-id>/
  wsd_assets/<language>/<method-id>/<snapshot-id>/

Fluency-Workspace/runs/<language>/<mode>/<run-id>/
Fluency-Workspace/releases/<language>/<mode>/<release-id>/
```

Each raw asset directory contains `artifact.json` using a shared manifest
contract:

```text
schema_version        artifact manifest version
artifact_kind         sentence_bank | embedding_cache | menu_snapshot | ...
language              BCP-47/ISO language code, or null for multilingual data
mode_scope            null unless the source is intrinsically mode-specific
provider              opensubtitles | spanishdict | google-gemini | ...
snapshot_id           immutable human-readable identifier
content_files         relative path, sha256, bytes and record count
source_uris           source URLs when known
license               known value or explicit unknown
created_at            original creation time when observed
recovered_at          migration recovery time
provenance_status     observed | reconstructed | unknown
recovered_from        old repository path and audit commit
producer              code commit, command and config when recoverable
inputs                 upstream artifact IDs and hashes
model                  provider/model/task/dimension/dtype when applicable
coverage               targets, records, misses and exclusions
notes                  limitations without silently changing semantics
```

Provider-only evidence belongs under a namespaced `provider_data` field. A
SpanishDict construction note must not add a Spanish-only field to the shared
sense-leaf schema. Optional fields remain optional and validation distinguishes
“absent by design” from malformed data.

The same contracts apply to Speech and Artist mode. Their provenance differs
(subtitle title/line versus artist/song/lyric location), but a sentence, menu,
embedding and WSD result use the same outer record shapes.

## Retained data assets

### OpenSubtitles harvested sentence bank — retain

Old files:

- `Data/Spanish/layers/subtitles/sentence_bank.jsonl`
- `Data/Spanish/layers/subtitles/word_candidates.json`
- `Data/Spanish/layers/subtitles/harvest_manifest.json`

Observed evidence:

- 42,650 unique sentence rows;
- 9,954 surface candidate entries;
- Spanish and English text, stable content ID, quality score, gate result,
  OpenSubtitles title ID, subtitle ID and line reference on each sentence;
- harvest run `2026-08-15T1257Z_harvest-v1`;
- source files were the aligned `OpenSubtitles.en-es.es`, `.en` and `.ids`
  files under `Data/Spanish/corpora/opensubtitles/`;
- the source scan skipped the first 32,000,000 aligned rows and stopped after
  row 34,000,000.

Hashes:

```text
sentence_bank.jsonl   f6c6c5903270d62575276d0ef21a2e00f7611c9f6762ed7875097ffea47527fe
word_candidates.json  13a65ae1466c30e17be8a6f76b4dd1c4629fec962f9dd93c6b05e3971641dee9
harvest_manifest.json ccbffd5e58e4e1c2ae7c47c3393e0e4a915795ea62e96de357edeea9ec4e27dd
```

Disposition:

- migrate the exact bank and occurrence map into a pinned sentence-bank
  snapshot;
- preserve both `clean` and `held` candidates—the labels describe the old
  harvest policy and are evidence, not permanent selection decisions;
- rebuild the final three-example selection in a run;
- do not migrate old example picks or sense assignments;
- record provenance as `reconstructed` because the exact corpus download URL,
  release identifier and license are not present in the harvest manifest;
- retain the original per-line OpenSubtitles identifiers rather than replacing
  them with a made-up movie title.

The three extracted raw corpus files are approximately 7.9 GB. They are useful
for a future re-harvest but are not required to reproduce the retained 42,650
sentence bank. Moving or hashing the full corpus is a separate, explicit raw
snapshot operation—not part of this quick migration pass.

### Gemini embedding cache — retain exactly

Old files:

- `Data/Spanish/layers/sense_vectors/vec.npy`
- `Data/Spanish/layers/sense_vectors/vec_index.json`
- `Data/Spanish/layers/sense_vectors/manifest.json`

Observed evidence:

- provider model `gemini-embedding-001`;
- task type `SEMANTIC_SIMILARITY`;
- 3,072 dimensions, normalized `float16` vectors;
- 276,724 exact-text index entries and a matching matrix shape of
  `(276724, 3072)` in the current cache;
- the manifest describes 17,861 vectors from the initial partial sense/sentence
  experiment, so the manifest count is stale relative to the current cache and
  must not be repeated as current coverage;
- keys are the exact text embedded, including the rendered sense form
  `"word" (POS): translation — context` and Spanish/English sentence strings.

Hashes:

```text
vec.npy        0614e32740bbf8d0850d6769547056684ba894d39583fb621fcc1d0fc7917c99
vec_index.json 3f654402a27e0b3cb347fc0737a65fd5a395daf1d8a081bda81be711732ad2cb
manifest.json  ddb1046f8e447a6fc427a0871f2b18458ab86d63a5889bfd78a9678d80dd20ff
```

Disposition:

- copy the three files byte-for-byte as one immutable embedding-cache
  snapshot; never copy the index without its vector matrix;
- generate a new outer `artifact.json` whose observed shape/count comes from
  the actual files and whose historical notes preserve the old manifest;
- record the creation run/API request IDs as `unknown`; the exact model/task
  settings are observed but the cache's full append history is not;
- use exact-text lookup across languages where model/task compatibility holds;
  do not label the cache Spanish-only merely because it currently lives in the
  Spanish tree;
- a menu edit creates a cache miss by exact text and never reuses a vector for
  changed content.

This cache contains reusable paid computation, not assignments. Keeping it
does not contaminate a new WSD run.

## Current WSD method snapshot

### Port as versioned code, discard its outputs

Pin the source implementation at audit commit
`23f1ad4387feb4a599815eaa6846e1201b5f402a` and identify the base classifier as
`sd-beto-cal-v5`. The reproducible stack is:

1. SpanishDict menu-order prior;
2. bridged occurrence-POS filter;
3. `se`-only clitic gate;
4. Gemini gloss/sentence cosine scoring;
5. gated BETO tuple override;
6. renderable-leaf repair;
7. the existing calibrator score;
8. optional Gemini low-confidence escalation;
9. optional aligned-English leaf correction.

Port behavior into shared components rather than copying `step_6e` as a new
monolith:

```text
wsd/core/              closed-menu candidates, scoring and disposition
wsd/signals/           menu prior, gloss cosine, token prototype, POS
wsd/correctors/        renderable leaf and aligned-English correction
wsd/es/                clitic evidence and SpanishDict↔UD POS bridge
wsd/providers/         Gemini embedding/cache client and optional escalation
wsd/methods/           immutable method configuration for sd-beto-cal-v5
```

The output is the shared WSD bundle already used by Fluency Next. Method code
may be Spanish-specific where the evidence is genuinely Spanish, but bundle
identity, disposition, hashing and import are language-agnostic.

### Alignment inconsistency — preserve, do not conceal

The current repository contains both:

- `speech-beto-cal-v5-pinned`, which admits `sd-beto-cal-align-v5`; and
- `speech-beto-cal-v5-noalign`, which places alignment in evaluation only.

The latest WSD handover says alignment is held out after grading 18 better, 13
worse and 19 lateral against v5. Therefore the migration will port the
alignment implementation and its method ID, but the base migration profile
will not silently enable it. Enabling it remains one explicit WSD method
configuration change and creates a different run/bundle.

### BETO runtime assets — retain as reproducibility assets

Files used by the current method include:

- `token_vec_cache/vecs.npy` (43 MB);
- `token_vec_cache/index.json` (29,236 exact sentence/surface keys);
- `token_prototypes/proto.npy` (44 MB);
- `token_prototypes/proto_index.json` and associated manifest/counts.

These are not Gemini embeddings and are not source truth. They are derived
model assets required to reproduce the current method cheaply. Preserve their
exact bytes inside the pinned WSD-method snapshot, with `reconstructed`
provenance, while separately supporting a clean rebuild. They never become
cross-run global fallback assets.

Known hashes include:

```text
token_vec_cache/vecs.npy       448bfefaab9925c700bff1c6525bd1255f7271f0af2651b00b4f196013ca2a1f
token_vec_cache/index.json     45ab567ae3c909a0b887f08837a1372989e17c4fe6b9b43fa12093a9e28a7a6a
token_prototypes/proto.npy     1ec0de1d85cdb608af3c8b579a90bbc4a1db8d62957c3d8a30e7d58456595777
token_prototypes/proto_index   146f2d9af3e34f2df4deaaab48df9588a0874405e016388ea45ea9659175500e
token_prototypes/manifest      cb1944ae304a38b31e8943e8bf511e8cb262ac56f32640628aaf8f717c20cdad
```

### Calibrator — port for reproduction, not as trusted confidence

The current calibrator is part of the method implementation, so its code and
model artifact are retained inside the method snapshot. Its manifest and the
latest handover explicitly say its dictionary-trained confidence bands are not
valid for real speech. Consequently:

- a reproduction run may emit its raw score and legacy band;
- the fields are marked `experimental`/`not_validated_for_speech`;
- release validation cannot use them to reject, escalate or hide examples by
  default;
- a future calibrated model gets a new method-asset ID rather than overwriting
  this one.

The exact current calibrator files are retained under these hashes:

```text
calibrator.joblib bf1ea4d6116dd7eeaf377428cf62deb2bce0c4af75d402764e698255e281dd55
manifest.json     fab2ef1dc7553b597b4be26f663b4aadb0ed9c70a64d06659590a7d785ac1930
```

## Source/menu and identity evidence

| Component | Disposition | Reason |
|---|---|---|
| `word_inventory.json` | retain as migration evidence; rebuild inventory | Needed for surface/order/legacy-ID comparison, but not clean source truth. |
| frequency CSVs | audit/pin one authoritative source | `SpanishRawWiki.csv` naming and values do not establish lineage. |
| SpanishDict cache snapshot | retain as pinned source evidence | Rebuild menus from provider evidence; do not import old sense shares. |
| compiled SpanishDict menu | compare/rebuild | Useful for parity and leaf-ID checks, but generated output is not canonical source. |
| Wiktionary menu/assignments | leave out of Spanish Speech default | May return later as an explicit provider, never silent fallback. |
| legacy surface IDs and migration maps | retain | Required for learner progress compatibility. |
| lemma assignments | discard | Lemma is lookup metadata, not card identity or a WSD output namespace. |

## Derived assignments and decks — discard

The following artifact classes are explicitly excluded from the new source
snapshot, even if they appear recent:

- `layers/sense_assignments/**`;
- `layers/sense_assignments_lemma/**`;
- `layers/unassigned_routing/**` when it contains a previous run's decision;
- all historical `runs/**/assignments/**`;
- legacy Gemini classifications and distributions;
- `example_picks/**`, `examples_raw.json` and compiled example choices;
- `vocabulary.json`, `vocabulary.index.json`, `vocabulary.examples.json` and
  their historical run copies;
- inherited/provisional sense weights;
- the evidence-profile pointer and mutable active-run pointer.

Their existence can be listed in an audit report, but their content cannot
author a new card, example or sense.

## Optional Spanish product layers

The mature repository contains useful behavior that French does not yet
exercise: morphology, attached-clitic analysis, conjugation/reverse cues,
SpanishDict usage/construction notes, MWEs, synonyms/antonyms, cognates,
loanword/proper-noun routing and personalised frames.

None is copied during the source-preservation pass. Each later receives one of
three outcomes:

1. rebuild behind a shared typed enrichment contract;
2. preserve a source snapshot but regenerate the derived layer;
3. deliberately cut because it no longer improves the product.

An absent optional layer must produce a valid simpler card. A malformed layer
must fail validation loudly. No optional layer may change surface identity,
silently exclude a card, or introduce a provider-specific required field.

## Dead architecture to avoid reintroducing

- one giant normal-pipeline script coordinating mutable repository paths;
- stages that both generate evidence and assemble the live app deck;
- author selection based on a global prompt-priority registry;
- unions of several accepted WSD generations;
- fallbacks to a shared token/model cache without a declared asset hash;
- source files, run products and active releases in the same directory tree;
- service-worker cache bumps as part of data correctness;
- language forks where a provider adapter or configuration field is enough;
- treating Speech and Artist records as unrelated schemas.

## Phase 0 result

The retain/rebuild/cut policy is now concrete enough to proceed. The first
implementation gate remains identity and learner progress compatibility:
measure the current live Spanish surfaces and `surface/v2` IDs against Fluency
Next canonical IDs, then produce an exception/collision report before choosing
the published alias strategy.

No asset copy should begin until the destination manifest contract and identity
crosswalk are validated. This prevents the preserved sentence/embedding assets
from acquiring another ad hoc directory or identifier scheme during migration.
