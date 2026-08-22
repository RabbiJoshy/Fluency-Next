# Wiktionary menus against the SpanishDict WSD baseline

## Decision

The current SpanishDict pipeline is the quality and architecture baseline. The
old French implementation is not being ported as a pipeline. It is consulted
only for already-discovered French/Wiktionary edge cases such as accent-sensitive
identity, ambiguous form-of targets, elisions, contractions, and pronominal
forms.

The French menu source is the English-language edition of Wiktionary as
structured by Wiktextract/Kaikki. This matters: the target entries are French,
but the glosses consumed by cross-lingual WSD must be English. A French-edition
Wiktionary extract with French glosses is not an interchangeable input.

## Structural mapping

| SpanishDict baseline | Wiktionary/Kaikki normalization | Result |
|---|---|---|
| surface card | inventory `card_id` + `surface_key` | identical surface-only identity |
| analysis headword | direct Kaikki `word`, or structured `form_of.word` / `alt_of.word` | explicit candidate headword |
| analysis part of speech | Kaikki `pos` | same `(headword, POS)` tuple boundary |
| dictionary leaf ID | Kaikki sense `id`; content-derived ID only when absent | stable closed-menu leaf |
| English translation/context | English `glosses`, `raw_glosses`, qualifier, tags and topics | retrieval text plus inspectable context |
| dictionary example | Kaikki sense `examples` | preserved as evidence, not mixed with harvested sentences |
| dictionary source/run | adapter ID, edition, snapshot label and SHA-256 | exact reproducibility |

For a surface such as `suis`, structured form-of targets can expose both
`être|verb` and `suivre|verb`. For a homograph such as `est`, a direct lexical
analysis and an inflectional path to `être` can both survive. WSD chooses between
the explicit tuples; neither a lemma field nor file order chooses for it.

## Spanish WSD layers that carry over

- closed-menu sentence-to-leaf embedding retrieval;
- independent contextual-token voting over `(headword, POS)` tuples;
- leaf selection inside the winning tuple;
- full score, gap, model, and decision-path evidence;
- retain/reject/abstain disposition selected per run;
- aligned-English sparse leaf correction where a frozen French panel validates
  it;
- path-specific confidence calibration trained on French Wiktionary decisions;
- immutable assignments joined by `card_id`, `sentence_id`, `menu_analysis_id`,
  and `sense_id`;
- no old-method union, priority registry, or cross-run fallback.

## Layers that require a provider or language adaptation

- SpanishDict's short translation plus structured context becomes Wiktionary's
  freer English gloss plus tags/topics/qualifiers. Retrieval stays shared; gloss
  parsing is provider-specific.
- SpanishDict `used with` and empty-leaf repair cannot be copied literally.
  Wiktionary leaf repair needs measured rules over its own tags and gloss shape.
- BETO prototypes, the Spanish calibrator, Spanish clitic gates, and their
  thresholds are not portable artifacts. The algorithms are portable; French
  models and thresholds must be benchmarked.
- English-word alignment is structurally portable, but matching an aligned word
  to the head of a free Wiktionary gloss needs a French-menu benchmark before it
  is enabled.

## Current normalization policy

- Preserve all semantic leaves with a non-empty English gloss.
- Treat `form-of` and `alt-of` senses as structured routes to a headword, not as
  learner-facing sense leaves.
- Bind every structured route to the source entry's compatible target POS.
  Ordinary morphology preserves POS (`verb → verb`, `pron → pron`, and so on);
  contractions may resolve to article/preposition analyses.
- Reject abbreviation and initialism expansion unless the entry is explicitly
  a contraction, and require redirect source case to match. Direct semantic
  entries are unaffected. This removes `de → dame`, conjugated-form noun
  leakage, and lowercase `cette → Sète` without flattening real ambiguity such
  as `suis → être|verb` versus `suis → suivre|verb`.
- Preserve rare, regional, archaic, topic, qualifier, etymology, and example
  metadata. Do not silently discard it before the audit establishes a policy.
- Preserve accents and punctuation in surface identity; never accent-fold a
  lookup.
- Follow only structured redirects, with bounded depth and cycle detection.
- Emit every inventory card. Missing dictionary coverage is an explicit
  `no_menu`, never a fallback to the first analysis or an old dataset.

## Known quality difference

The topology fits the Spanish architecture well: both sources can represent
headword/POS tuples containing closed leaves. Wiktionary is weaker as a curated
learner menu. Its English glosses vary more in length and style, and provider
constraints are less uniform. The benchmark therefore needs to measure gloss
normalization, tuple prototypes, alignment, and calibration separately rather
than assuming Spanish thresholds transfer.
