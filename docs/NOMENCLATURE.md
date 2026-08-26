# Nomenclature

Words worth using precisely, because each one below was confused for another at
some point and the confusion cost something. Use these when talking about the
system, including with an LLM.

## provider

**A sense-menu source.** SpanishDict and Wiktionary are providers. A provider
supplies the inventory of meanings a word may have, and the metadata attached to
them.

A provider is **not** a language and **not** a corpus:

| | |
|---|---|
| **provider** | where the *meanings* come from — SpanishDict, Wiktionary |
| **language** | `es`, `fr`, `pt` |
| **mode** | speech, lyrics, artist — where the *sentences* come from |
| **source** | ambiguous; avoid it. Say provider, corpus, or snapshot. |

The distinction matters because they do not line up. SpanishDict serves one
language. **Wiktionary serves French, Portuguese and everything after.** So a
change that works "for Portuguese" usually means it works for Wiktionary, which
is a much larger claim — and a change that works "for Spanish" often means only
SpanishDict, which is a much smaller one.

Ask *"is this provider-agnostic?"* rather than *"does this work for other
languages?"* — the second question hides which of the two you meant.

## provider parity

**The requirement that a concept exists for every provider that can express it.**
A signal, gate or feature built for SpanishDict alone is not finished; the
Wiktionary equivalent ships with it, or a recorded reason says why there is none.

Providers encode the same concept differently, so parity is achieved by adapters
rather than by sameness. The companion note is the worked example: SpanishDict
writes prose in `context` (`used with "de"`, 587 senses), Wiktionary emits a
structured `+obj` template (438 senses in Portuguese). One `companion` feature
family, two extractors, one gate that cannot tell which it is reading.

## contract, method, carriage

Three different claims about an artifact that sound like one:

- **contract** — the shape it speaks. "This release speaks v7's dual view."
- **method** — what computed the decisions inside it. "These were chosen by v7."
- **carriage** — how they got there. "These were migrated, not recomputed."

A release can speak v7's contract over decisions computed by v5 and carried
forward. Reading `retained_materialized_assignments` — a carriage label — as a
method claim once led to the conclusion that the Rosalía releases were stranded
on v5. They were not.

## adapter and engine

- **adapter** — absorbs the irregularity of one provider, corpus or frequency
  list, and emits a neutral contract. There are nine.
- **engine** — everything below the adapters: one WSD, one selection, one release
  path, shared by every language and mode.

"Put it in an adapter" means *this varies by provider or corpus*. "Put it in the
engine" means *this is the same everywhere*.

## the specificity ladder: leaf, glosskey, tuple, unresolved

How precisely a decision is published:

| | |
|---|---|
| **leaf** | the exact sense — *casa* = a dwelling |
| **glosskey** | the meaning, not the shade — *casa* = house |
| **tuple** | lemma and part of speech only — *casa* = a noun |
| **unresolved** | no claim; stays in the denominator, never renormalised away |

**Backing off** is moving down this ladder. Note that how much the middle rung is
worth is provider-dependent: `glosskey` is nearly inert on SpanishDict and
carries 16–22% of decisions on Wiktionary.

## budget and limit

- **budget** — a number that is *spent*. `wsd_budget_per_card` decides how many
  sentences reach a paid model.
- **limit** — a number that is merely enforced. `display_examples_per_card`
  costs bytes.

Only the spendable one is called a budget. Calling both a "cap" is what let a
change to the expensive number look like a change to the cheap one.

## pool

**A named, described set of harvested sentences.** Flat — no cards in it, so one
pool serves any inventory. Everything below a pool narrows within it, which is
why "every example on this card came from one pool" holds by construction.

## run, release, deck

- **run** — a directory of immutable stages under
  `<workspace>/runs/<language>/<mode>/<run-id>`. A run is the unit of work.
- **release** — what is published from a run, under `releases/`. Validated,
  activated by an explicit pointer, never edited in place.
- **deck** — `deck.json` inside a release: the app-facing cards. It is the
  *contents*, not the container.

"Rebuild the deck" is ambiguous. Say which: a new run, a new release from an
existing run, or a re-render of the deck file.

## candidate, assignment, example

Three narrowings, three words, and saying the wrong one hides a stage:

| | | Portuguese run |
|---|---|---:|
| **candidate** | a sentence retained for a card by the harvest | 12,000 |
| **assignment** | a candidate a classifier reached a decision on | 2,000 |
| **example** | an assignment selected to appear on the card | 600 |

Only the middle step costs money. See **budget**.

## snapshot

**An immutable, content-hashed copy of an external input**, under
`<workspace>/raw/`. A snapshot is not the thing it copies and not a set derived
from it:

- **corpus** — the upstream body of text (OpenSubtitles, Tatoeba)
- **snapshot** — a pinned copy of some of it, with hashes and licence
- **pool** — a named set of sentences harvested from a snapshot

## stage, not step

The pipeline has six **stages**, numbered and immutable. Avoid "step"; it drifts
between meaning a stage, a substep, and a CLI invocation. Name stages by name --
`sense_menu`, `sentence_harvest` -- rather than by number alone.

A stage with output refuses to be rebuilt. Create a new run instead.

## bundle

**A WSD executor's output file, before import.** A bundle is *not* stage 04.
`pipeline wsd-import` validates it and publishes it into
`stages/04_wsd_assignments/output/assignments.jsonl`, which is what the release
builder reads.

Skip the import and the release reports "no WSD stage was present" -- truthfully,
and confusingly, because the bundle exists.

## gate, filter, scorer

- **gate** — rejects on a checkable condition. The companion gate asks whether a
  required word is present.
- **filter** — narrows a set, usually by comparing attributes. The POS filter
  compares a tag against dictionary categories.
- **scorer** — ranks candidates by a continuous score. The gloss scorer.

The distinction is not pedantic. A gate's negative means *this is impossible*; a
filter's empty result means *nothing matched*, which must be read as **no
evidence** rather than **reject everything**. Reading it the second way is what
turned the POS filter into a silent no-op on the commonest words.

## abstain, unresolved, unassigned

Three ways of having no answer, at three different places:

- **abstain** — the classifier declined to choose. A property of a decision.
- **unresolved** — the lowest rung of the specificity ladder: a decision was
  made but nothing may be published. A property of a publication.
- **unassigned** — an example with no sense attached to it, because WSD did not
  run or did not reach it. A property of a card.

A deck can be entirely unassigned with no abstentions anywhere, which is what
every Portuguese release before WSD was.

## enrichment

**An optional per-word layer joined by headword or card, sitting beside the
pipeline rather than on it.** Conjugations are one; pronunciation would be.

Enrichments are per-*word* facts. A sense menu holds per-*sense* facts. Putting a
per-word fact in the sense menu duplicates it across every leaf and ties a
pre-WSD fact to a structure that exists to enumerate meanings.

## native, migrated

- **native** — a decision computed in this run.
- **migrated** — a decision computed earlier and carried into the current
  contract by a bridge.

Both are legitimate to ship. `wsd/provenance.py` reports the split per release,
because "this deck is on v7" is true of a fully migrated deck in a way that
misleads. See **contract, method, carriage**.

## tuning set, holdout

- **tuning set** — data you look at repeatedly while developing. You fit to it,
  deliberately or not.
- **holdout** — data you touch once, at the end, to find out whether it worked.

Once a set has been tuned on it is not a holdout again. **Rosalía was tuned on
during v7**, so it is a regression check -- did this break what worked -- rather
than a score. Portuguese has never been tuned on.

## card identity

**The observed surface form.** `card_id = f(language, surface_key)` and nothing
else. Not the lemma, not a sense, not a rank.
