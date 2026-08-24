# Decision 0020 — Portuguese language onboarding and non-unique Kaikki sense IDs

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
