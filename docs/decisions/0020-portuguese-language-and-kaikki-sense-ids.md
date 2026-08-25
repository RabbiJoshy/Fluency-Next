# Decision 0020 — Portuguese speech language, harvest pools, and the WSD budget

## Decision

Add Portuguese (`pt`) as a Speech language, sourced from a published two-column
frequency list rather than an analysed lexicon, and repair the shared Kaikki
adapter so that a non-unique provider sense ID falls back to Wiktionary's own
`senseid` list instead of failing the build.

## Frequency source

Portuguese uses the FrequencyWords OpenSubtitles 2018 `pt_br` 50k list
(MIT licence, `surface<space>count`, one line per surface). A new adapter
`published-surface-frequency-list/v1` reads that shape.

This matches the established house default rather than introducing one: the
reference repository's Spanish, English, and Dutch inventories are all the same
two-column OpenSubtitles shape. French is the exception, not the rule — it uses
Lexique, whose value is its lemma and grammatical analysis columns, and
`inventory/lexique.py` deliberately discards exactly those. The frequency figure
French actually consumes is subtitle-derived anyway.

Counts are summed, not maxed, when normalization maps two published rows onto
one card. Unlike Lexique's repeated analysis rows, each line here is a distinct
set of corpus occurrences.

Brazilian and European lists share 80.9% of their top 10,000 surfaces, with
divergence confined to `tu`-conjugations (`foste`, `fazes`, `disseste`) and
spelling (`facto`, `bebé`). The deck is not split by variant.

## Portuguese is shaped like Spanish, not French

Portuguese has no French-style elision, so `config/languages/pt/tokenization.json`
follows the Spanish policy shape. Accents are contrastive at the surface
(`pais`/`país`, `esta`/`está`, `e`/`é`) and are never folded.

Hyphenated clitics (`dá-me`, `vê-lo`) and mesoclisis (`far-me-ia`) are preserved
verbatim by the normalizer. The frequency list contains no hyphenated surfaces —
its tokenizer split them — so no clitic card exists in the inventory. This does
not break matching: `SurfaceMatcher.find_cards` anchors on word-boundary
lookarounds rather than the token pattern, so `Dá-me o livro` correctly yields
the `dá`, `me`, and `livro` cards.

`sense_menu/kaikki.py` previously imported the French normalizer directly. It now
resolves both the surface normalizer and the typography canonicalizer from the
run's language. This mattered: French rewrites `d'água` to `d’água`, which would
have keyed the Portuguese menu differently from the Portuguese inventory and
silently failed the join.

## Non-unique Kaikki sense IDs

Kaikki flattens a sense's `senseid` list to its FIRST entry and appends a counter
when that collides, without re-checking the counter against IDs it has already
emitted. Nested sub-senses therefore share one `id`:

    senseid=['pt:not']                          id=en-não-pt-adv-pt:not
    senseid=['pt:not', 'pt:double negative']    id=en-não-pt-adv-pt:not1
    senseid=['pt:not', 'pt:emphatic negation']  id=en-não-pt-adv-pt:not1
    senseid=['pt:not', "pt:isn't"]              id=en-não-pt-adv-pt:not1

Wiktionary's own identifiers are not ambiguous. Kaikki's flattening is what
collides, and the discarded tail is the discriminator.

Measured: 16 of 445,244 Portuguese entries (0.004%) and **20 of 402,395 French
entries**. Rare, but concentrated on common words — `não`, `o`, `um`, `seu`,
`onde`, `levar`, `passar` in Portuguese; `canon`, `charge`, `voix`, `roi`,
`cellule`, `cas`, `disque` in French. This is a latent defect in the shared
adapter that Portuguese surfaced first; the 200-surface French audit has not yet
reached an affected word.

Resolution order, applied per `(headword, part_of_speech)` analysis:

1. Unique provider `id` — used verbatim. **This is the unchanged common path, so
   every existing French sense ID is bit-for-bit stable and nothing re-keys.**
2. Colliding `id`, distinct `senseid` — rebuild as
   `en-{headword}-{lang}-{pos}-{senseid joined by |}`.
3. Colliding `id` and colliding `senseid` — content hash over sense keys,
   glosses, raw glosses, tags and topics.

The content hash deliberately **excludes the sense's ordinal**. The previous
fallback included it, which made identity positional: reordering an entry
upstream would silently re-key a card and move learner progress onto a different
meaning.

Verified on the real snapshot: all 18 Portuguese collision groups resolve, and
`não` builds nine senses across adv/intj/noun with no content-hash fallback
required.

## Verified run

`runs/pt/speech/20260824T180000Z-00b70001`:

- Stage 01 inventory — 200 surface cards from `pt_br_50k.txt`
  (`sha256:a61d6f2e…`), zero rejected rows out of 50,000.
- Stage 02 sense menu — 200/200 cards ready, 0 without menu, 422 analyses,
  1,900 senses, 3 scan passes, no fallbacks.

## Not decided here

WSD. `config/wsd/languages/pt-v1.json` and `config/wsd/models/pt-rehearsal-v1.json`
exist as stubs with `execution_status: blocked_pending_benchmark`, and every
model revision is unpinned. Portuguese follows decision 0019: publish an
explicitly unassigned audit deck first.


---

## Harvest pools

A pool is a **flat set of sentences with no cards in it**. Card-indexing would
weld a pool to the inventory it was built against, so a pool built for 200
surfaces would be useless at 5,000. Keeping cards out is what lets one European
pool serve any word list.

Everything below a pool only narrows *within* it — the per-card WSD budget, WSD
abstaining, the display limit — so "every example on this card came from one
pool" holds by construction rather than by bookkeeping. Pools may overlap
freely; which pool a card drew from is a property of the run's choice, not of
the sentence.

`config/pipelines/.../*.json` is unchanged by this. A run that names no pool
harvests inline exactly as before, which is what every existing run does: one
implicit, unnamed pool.

Registered for Portuguese:

| Pool | Sentences | Variety |
|---|---:|---|
| `pt-opensubtitles-european-2015plus` | 10,909 | european, 100% from 2015-2017 |
| `pt-tatoeba-brazilian` | 7,973 | brazilian |

Pool sentence banks are **hard-linked** to the run's copy where the filesystem
allows it. Both files are immutable by contract, so sharing the inode costs
nothing. This is a stopgap for the shared content-addressed store, which would
additionally deduplicate across runs — measured at 59% duplication over three
Spanish runs, with two runs byte-identical at 32 MB each.

## The WSD budget, and why it is not called a cap

Two numbers narrow a run and they are not comparable in cost:

- `wsd_budget_per_card` (was `candidate_cap_per_surface`) — sentences per card
  handed to WSD. Every one may be embedded or sent to a model, so it is **spent**.
- `display_examples_per_card` (was `examples_per_surface`) — examples the card
  shows. Costs bytes.

Calling both a "cap" invited one specific mistake: reasoning about the cheap
number while changing the expensive one. Only the spendable number is a budget.

The real exposure was never the naming. `candidate_cap_per_surface` had
`minimum: 3` and **no maximum**, `surface_limit` had no maximum, and their
*product* was computed nowhere. `max_wsd_units_per_run` now bounds it, checked
at plan time, and the projection is printed before any stage runs:

    WSD spend: 200 cards x 60 sentences = 12,000 units (ceiling 25,000)

Both legacy key names are still read, so profiles written against the old
contract keep working. A *missing* budget is refused rather than defaulted —
an unstated budget must never silently become unlimited.

## The funnel ledger

The harvest report recorded `accepted_matches_before_cap` only as an aggregate;
per surface it showed the number that *survived* the cut. The pre-cap count per
word was never written down, which is what made the funnel unreadable.

Per card the report now records `matched_before_budget`, `discarded_by_budget`,
`budget_rule` and `display_rule`. On the European run:

    13,422,906 matched  ->  12,000 kept  ->  600 shown

A 99.91% discard rate that was previously invisible.

## European Portuguese corpus

`opensubtitles-v2018-en-pt`, sliced to lines 27,935,533+ (`-2015plus`).

OPUS separates `pt` from `pt_br` and the separation is real. Measured on
200,000-line samples: the European progressive *está a fazer* leads the
Brazilian gerund 2.6:1 in `pt` and trails it 1:134 in `pt_br`;
`casa de banho`/`autocarro`/`comboio` outnumber `banheiro`/`celular` 363:14.
The shipped deck contains **37 European progressives and 0 Brazilian**.

**The slice is the point, not an optimisation.** Harvesting ranks candidates by
easiness score and ignores release year entirely, so scanning the full corpus
would happily fill a deck with 1950s dialogue. Restricting the input is what
makes the deck recent. The corpus is sorted by year ascending, so recent
material is a contiguous tail. It also cut the scan 6.3x.

Every example on the shipped deck is from 2015 (259), 2016 (249) or 2017 (92),
against the Spanish deck's ceiling of 2011.

`v2024` was investigated and rejected for now: its moses distribution ships no
`.ids`, and deriving one from the alignment XML was **measured wrong** — 63
spurious and 62 missing lines per 300,000 against v2018's real `.ids`. Moses
alignment is positional, so a single spurious line misattributes every sentence
after it. The correct v2024 path is `raw/pt.zip` + `raw/en.zip`, which is 39 GB
and a new adapter. Pools make adding it additive rather than a migration.

## Not decided here

WSD. Portuguese follows decision 0019 and ships an explicitly unassigned deck:
`pt-speech-european-200-unassigned-20260825`, 200 cards, 600 examples, active.
