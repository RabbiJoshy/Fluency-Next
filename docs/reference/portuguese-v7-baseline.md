# Portuguese v7 baseline, 2026-08-25

The first WSD measurement on Portuguese. **Nothing here is tuned**: v7's
parameters were fitted on Rosalía, so this establishes a baseline rather than
being validated against one. Treat it as evidence to inspect, not a score.

Run `20260825T012303Z-c82782e3`, profile `pt-v7-1`, Wiktionary menu,
`pt_core_news_lg@3.8.0`, European OpenSubtitles 2015–2017.

## What ran

| | |
|---|---|
| Cards | 200 |
| Candidates harvested | 12,000 (60/card) |
| Sampled for scoring | 2,000 (10/card) |
| Assigned | 2,000 — 1,833 disambiguated, 167 deterministic |
| Embeddings created | 2,736 into `embeddings/pt/` |

## The POS bridge earns its place

Measured on 2,692 real occurrences, real tagger, real menus:

| | occurrences losing every sense |
|---|---:|
| Unbridged (UD tag == Wiktionary category) | **916 (34.0%)** |
| Bridged | **84 (3.1%)** |

Wiktionary files `do`, `ao`, `da`, `na` **only** as `contraction`, which
Universal Dependencies has no tag for, and like SpanishDict it has no `aux`.
These are top-fifty words. Compare the Spanish figure recorded in
`wsd_dead_ends.md`: bridged, 1 kill in 63 fires (~2%).

## The specificity ladder has signal, and no thresholds

All three minimums are `0.0` (`thresholds_unmeasured_defaults_emit_leaf`), so
every decision emits at `leaf`. But the axes are not degenerate: **margins differ
on 77.8% of assignments**, median tuple−leaf gap 0.182, max 0.498.

Simulated over the real margins:

| leaf / glosskey / tuple | leaf | glosskey | tuple | unresolved |
|---|---:|---:|---:|---:|
| 0.0 / 0.0 / 0.0 *(current)* | 100% | — | — | — |
| 0.1 / 0.05 / 0.02 | 69% | 16% | 14% | 1% |
| 0.2 / 0.10 / 0.05 | 52% | 20% | 26% | 3% |
| 0.3 / 0.15 / 0.05 | 40% | 22% | 35% | 3% |
| 0.5 / 0.30 / 0.10 | 26% | 17% | 51% | 6% |

The unresolved share stays low (1–6%) throughout, so backing off moves between
rungs rather than giving up — the shape you would want.

**This contradicts a SpanishDict finding.** `glosskey` removes only 13% of
SpanishDict candidates and was called a near no-op there. On a Wiktionary menu it
carries 16–22% of decisions at every setting. SpanishDict leaves are English
near-synonyms of one meaning (bench/pew/stool/desk under one `seat` context);
Wiktionary glosses are definitions and collapse differently. The middle rung is
real here.

## What would settle the thresholds

Hand-graded Portuguese cards, which do not exist. Nothing above says which
setting is *right* — only that there is signal to threshold on, and roughly where
the interesting range sits.

## The European list contains clitics; the Brazilian one does not

Measured while deriving surface exclusions for a 2,000-card run. The European
`pt_50k` list contains **49 hyphenated clitic forms in its top 2,000** --
`deixa-me`, `diz-me`, `vê-lo`, `senta-te`, `lembro-me`, `parece-me`. The
Brazilian `pt_br_50k` list contains **none at any depth**: its tokenizer split on
hyphens.

That is a difference between the two lists, not between the two varieties, and it
matters twice over.

**They are kept.** Enclisis is exactly the construction a European learner needs,
and it is what most audibly separates the two varieties. Excluding them because
they are inconvenient would remove the point of the deck.

**They have no Wiktionary entry.** Wiktionary lists `dizer` and `me`, not
`diz-me`, so these cards reach the sense-menu stage with nothing to attach. At
200 cards this never arose; at 2,000 it affects 49 surfaces, which will appear as
`cards_without_menu`.

Neither behaviour is wrong, and the pipeline already publishes a card with an
empty menu explicitly rather than dropping it. But it is an open question worth
deciding rather than discovering: whether a clitic surface should resolve to its
base verb's menu, carry the pronoun as separate evidence, or stay menu-less.
