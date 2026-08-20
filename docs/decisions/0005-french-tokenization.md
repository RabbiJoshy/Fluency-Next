# 0005: French tokenization and dictionary lookup routing

- Status: Accepted
- Date: 2026-08-20

## Decision

Tokenize French with explicit precedence: approved surfaces and multiword
expressions first, grammatical French splitting second, ordinary orthographic
tokens third, and retained ineligible evidence last.

Recognized elisions become a clitic surface plus the following surface. An
approved lexicalized apostrophe form remains whole. Approved lexical hyphenated
forms remain whole, while recognized inversion and imperative clitic groups are
split. An unrecognized hyphenated form is retained for review rather than
guessed. The euphonic inversion `t` is retained as rejected structural evidence.

`au`, `aux`, `du`, and `des` remain surface cards. Their components and
grammatical roles are structural metadata and do not cause component dictionary
senses to be copied into the surface's sense menu.

Dictionary lookup always begins with the exact surface. Elided clitics receive
explicit secondary expansion candidates. No heuristic stemming or lemmatization
is performed in this layer.

## Legacy evidence

The old Lexique conversion produced 10,000 surfaces but 12,096 surface/lemma
rows. It contained 11 apostrophized forms, 91 hyphenated forms, 12 spaced forms,
and incomplete fragments including `parce qu` and `est-ce qu`. The new contract
preserves intentional lexical units while quarantining incomplete fragments and
removing lemma duplication from card identity.

## Consequences

- Token decisions, rejected material, parent spans, and canonical offsets remain
  inspectable.
- Adding an approved surface can affect segmentation, so the approved registry
  hash must be a tokenizer-stage input.
- Capitalization is not used to discard possible proper nouns.
- Numeric, mixed, URL, and email tokens are retained but ineligible for Speech
  v1 cards.
- Future language adapters can implement different rules without changing the
  shared token record.

