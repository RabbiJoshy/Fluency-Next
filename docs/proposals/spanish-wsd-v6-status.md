# v6 in Fluency-Next: what is done, what to run, what to iterate on

Written to close out the porting session. The method itself is documented in the
reference repository at `docs/reference/wsd_design.md`; this file is only about
what exists here and how to drive it.

## What is in the repo

**The method**, as three roles rather than seven stages:

| role | job | module |
|---|---|---|
| CONSTRAIN | remove candidates that cannot be right | `wsd/languages/spanish.py` (existing policy) |
| RANK | one score over the survivors | `wsd/gloss_scoring.py` (existing seam) |
| COMMIT | decide *how specific* an answer to emit | `wsd/commit.py` (new) |

Plus `wsd/multiword.py` (multiword senses as competing candidates) and
`wsd/sampling.py` (per-surface execution cap).

**Fixed on the way**: the inherited AUX bridge bug. SpanishDict has no AUX
category and files auxiliaries as VERB while the tagger emits AUX, so the POS
filter was silently a no-op on `haber, ser, estar, deber, saber`.

**Deliberately not ported**, each recorded with its reason in `es-v6-1.json`:
the calibrator, leaf repair as a stage, the BETO token-prototype vote, and
domain-weighted ranking.

## Running it

```bash
W=../Fluency-Workspace
PROFILE=config/pipelines/es/speech/v6-2000x3.json     # or v6-500x3.json

PYTHONPATH=src python3 -m fluency.cli pipeline plan --workspace $W --profile $PROFILE
# take the printed RUN id
PYTHONPATH=src python3 -m fluency.cli pipeline inventory  --workspace $W --run-id $RUN --language es --mode speech \
  --snapshot $W/raw/frequency/fluency-2026-07-28-surface-ranking-v1 --snapshot-id fluency-2026-07-28-surface-ranking-v1
PYTHONPATH=src python3 -m fluency.cli pipeline sense-menu --workspace $W --run-id $RUN --language es --mode speech \
  --snapshot $W/raw/spanishdict/spanishdict-2026-08-19-cache-v1 --snapshot-id spanishdict-2026-08-19-cache-v1
PYTHONPATH=src python3 -m fluency.cli pipeline harvest    --workspace $W --run-id $RUN --language es --mode speech \
  --source retained-opensubtitles=$W/raw/opensubtitles-retained/retained-opensubtitles-2026-08-15-harvest-v1

# WSD runs outside the pipeline and is imported, like the lyrics path
PYTHONPATH=src python3 -m fluency.speech.wsd_execute --run-dir $W/runs/es/speech/$RUN \
  --out $W/raw/wsd/es-v6-$RUN/bundle.json \
  --multiword-inventory $W/raw/mwe/mwe-merged-2026-08-23-v1/mwe_merged.json \
  --execution-cap 5

PYTHONPATH=src python3 -m fluency.cli pipeline wsd-import        --workspace $W --run-id $RUN --language es --mode speech --bundle $W/raw/wsd/es-v6-$RUN/bundle.json
PYTHONPATH=src python3 -m fluency.cli pipeline build-run-release --workspace $W --run-id $RUN --release-id <id> --language es --mode speech
```

Run `wsd_execute` in a terminal, not inside a tool call: at full scale it is
tens of minutes.

## Costs, measured

Gloss vectors scale with how many **cards** are scored; sentence vectors with
the **cap**. Only the second is a lever, and it is bounded because the retained
bank holds 42,650 sentences in total.

| scope | texts | note |
|---|---|---|
| 500 cards, cap 10 | 6,063 | done |
| 2,000 cards, cap 3 | 12,254 | done |
| 9,999 cards, cap 5 | ~57,000 | ~26 min, one time |
| 9,999 cards, cap 10 | ~68,700 | ~31 min |

The cache at `<workspace>/embeddings/es/exact-text-gemini-embedding-001.npz` is
shared per language, not per run. That is deliberate: gloss vectors belong to
the dictionary and sentence vectors to the corpus, so both outlive any run. A
per-run cache silently re-embeds everything and destroys the amortisation --
this was a real bug and is fixed, but it is worth not reintroducing.

**Cap 5 is the recommended default.** With three examples per surface it leaves
adequate headroom, and it saves only ~17% over cap 10 because the gloss side
dominates.

## Known, not fixed

- **Menu coverage falls off fast.** `no_menu` is 1% over the top 500 surfaces
  and 24% over the top 2,000. Those cards publish with unassigned examples
  rather than being dropped, which is correct, but it is the number that decides
  how far down the frequency list is worth going.
- **A harvested "English" translation is actually Portuguese** in at least one
  row. Source-data quality in the retained bank, not WSD.
- **COMMIT's thresholds are unmeasured and default to zero**, i.e. always emit a
  leaf. The gloss backoff is validated (78% -> 85% precision on a hard panel);
  the tuple trigger is NOT -- the tuple margin proved non-monotonic against
  tuple correctness. Do not raise `tuple_minimum` on the margin alone; method
  agreement is the measured alternative and is not implemented here.

## Where to iterate on the algorithm

The replaceable boundary is:

> (surface occurrence + context + closed menu + optional evidence)
> -> assignment or explicit disposition

Everything upstream (harvest, menus, sampling) and downstream (selection,
release, app) is independent of how the decision is made. To try a different
method, replace the `GlossScorer` / `CandidatePolicy` / `CommitPolicy`
implementations or write a new executor emitting the same bundle. Nothing else
needs to change.

The open research question, and the honest state of it: the remaining error is
overwhelmingly **near-synonym choice within the right lemma and POS**. Domain
labels, syntactic frames, aligned English and precomputed harm-triage were all
measured and none of them moved it. The one thing that reliably does is a model
that reads the sentence.
