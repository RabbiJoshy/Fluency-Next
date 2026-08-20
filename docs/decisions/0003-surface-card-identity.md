# 0003: Surface-card identity

- Status: Accepted
- Date: 2026-08-20

## Decision

A card represents one written surface form in one lexical language. Its identity
contains the identity-contract version, ISO 639 language code, unit type, and
normalized surface key. It does not contain a lemma, sense, part of speech, mode,
artist, corpus, rank, or dictionary source.

IDs use the prefix `card_{language}_` followed by the first 128 bits of a SHA-256
digest over an unambiguous JSON encoding of the complete identity tuple. The
current contract is `surface-card/v1` and the only supported unit type is
`surface`.

French surface keys use NFC Unicode, trimmed and collapsed whitespace, lowercase
letters, a canonical curly apostrophe, and a canonical ASCII word-internal
hyphen. They do not remove accents, fold ligatures, lemmatize, expand
contractions, correct spelling, or split tokens.

Token boundaries remain the responsibility of the later French tokenizer.

## Consequences

- Speech and Artist mode share the same French cards.
- Homographic senses and parts of speech attach to one surface card.
- Inflected forms remain distinct cards.
- Typographic apostrophe and hyphen variants do not create duplicate cards.
- IDs are deterministic and independent of input ordering or database state.
- Identity changes require a new contract version and an explicit migration.
- Cards are retired or redirected rather than silently reassigned or deleted.

