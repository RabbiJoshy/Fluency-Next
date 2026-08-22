# Spanish progress identity audit

## Purpose

Measure the real Spanish Speech identity state before choosing a Fluency Next
progress strategy. This is a read-only audit of the old repository at commit
`23f1ad4387feb4a599815eaa6846e1201b5f402a`. It does not alter localStorage,
Google Sheets, an active release or any source data.

## Intended identity

The intended Spanish product rule is already settled: one card per normalized
surface form. Lemma, headword, POS, sense, corpus, mode and artist are not card
identity.

Fluency Next currently represents that identity with:

```text
identity_version = surface-card/v1
identity_tuple   = [identity_version, language, "surface", surface_key]
card_id          = card_<language>_<128-bit SHA-256 prefix>
```

The old Spanish application intended to publish an eight-hex surface ID from
`md5("surface/v2:" + surface)[:8]`, wrapped by a progress key such as
`es0d6ffed1a` for Spanish Speech.

## What the live Spanish index actually contains

| Measurement | Result |
|---|---:|
| Compiled index rows | 10,749 |
| Unique normalized surfaces | 9,389 |
| Surfaces represented more than once | 1,315 |
| Rows with the intended eight-hex surface ID | 4,845 |
| Rows retaining a six-hex lemma-era ID | 5,904 |
| Duplicate main IDs | 0 |
| Clean inventory surfaces | 9,999 |
| Inventory surfaces absent from compiled index | 610 |

This means the conceptual surface migration was correct, but the compiled deck
did not finish the migration. Many surfaces still render as several lemma-era
cards. For example, `una` appears under `c72b0494`, `263b8c` and `d8b228`;
`para` appears under `af583826`, `96be55` and `63ff64`.

The clean migration must not preserve those duplicate cards. It must preserve
their progress IDs as aliases of one surface card.

## The existing migration map is not an executable source of truth

`Data/Spanish/id_migration.json` contains 21,350 directed entries. Following
the entries recursively produces:

- 10,500 keys that terminate at a current compiled card;
- 10,777 keys involved in cycles;
- 73 keys with a terminal ID absent from the current compiled index.

The old frontend avoided infinite loops by applying exactly one mapping pass
and setting a non-idempotent localStorage migration flag. That behavior must not
be ported. A future resolver must never depend on iteration order, a one-time
browser flag or repeated application of this map.

## Recoverable alias evidence

The current and four retained Spanish Speech deck indexes expose 17,326
historical card IDs with surface evidence. Only two IDs were reused for two
different surfaces across generations:

| Ambiguous old ID | Observed surfaces |
|---|---|
| `780764` | `atrás`, `sientes` |
| `f7bfce` | `brillantes`, `laboratorio` |

Treating the old migration map as an undirected evidence graph produces 9,417
components:

- 9,415 components containing 26,075 old IDs resolve to exactly one observed
  surface;
- two components containing ten IDs touch two surfaces because of the two
  historical six-hex collisions above;
- no component lacks surface evidence.

Within those two components, six IDs still have direct unambiguous surface
evidence and four are unobserved intermediate IDs. The two reused IDs remain
genuinely ambiguous without progress-row timing/release evidence.

The old assembler's own comments identify the cause: six-hex birthday
collisions plus insertion-order collision handling. This is exactly why an old
ID must be an alias, never the canonical identity in Fluency Next.

## Clitic aliases expose a second old-model problem

The compiled index contains 606 nested alias rows, covering 544 unique IDs.
Some attach the progress ID for a clitic surface to a base card—for example,
`dele` and `deme` are nested under the `de` card.

Fluency Next must preserve the surface identity rule here too:

- the legacy ID for `dele` resolves to the canonical `dele` surface card when
  that surface exists;
- it does not silently become progress on the `de` surface merely because the
  old presentation merged the two;
- a language-specific clitic relation may connect the cards as enrichment,
  without changing either identity.

This rule is reusable for French contractions and future language-specific
surface relations.

## Recommended identity and progress model

Keep the existing Fluency Next canonical card ID. Add a language-agnostic alias
registry whose records are immutable and evidence-backed:

```text
schema_version
alias_namespace       e.g. fluency-progress-legacy/v1
alias_key             full historical key such as es0d6ffed1a
language
mode                   speech | artist when the old key encoded a mode
canonical_card_id
surface_key
status                 resolved | ambiguous | retired
evidence               source file/release/hash and observation kind
provenance_status      observed | reconstructed | unknown
```

Rules:

1. Internal runs, menus, sentences, WSD bundles and releases use only the
   canonical long card ID.
2. Existing eight- and six-hex IDs are accepted only through alias records.
3. Every observed old ID for the same surface may resolve to the same card.
4. Several old progress records that resolve to one card are merged
   deterministically at read time; no Sheet write is required initially.
5. New progress writes use one canonical progress-key format after app
   compatibility is approved.
6. Alias resolution is one lookup, never recursive remapping.
7. Ambiguous aliases remain visible and do not auto-assign progress.
8. Speech and Artist share the canonical surface card; any mode distinction is
   a progress/activity field, not a different lexical identity.

Example canonical IDs:

```text
que          card_es_b528b5695f85520cf31558c0486f5ae4
atrás        card_es_d1e435c09537d2f97054de71dcdf32ae
sientes      card_es_5ce6de4165391bed50bd69eb6719a9f8
brillantes   card_es_a54c4191291854b5fd6384df927996a5
laboratorio  card_es_f5c63015e2aa33109a6ef029321e4e0b
dele         card_es_3f1e4a736a060d7d69d7ec7b7d005565
de           card_es_2ab466ba4028ec8044825e70437a6b6b
```

## Treatment of the two reused progress IDs

Do not guess. Preserve each as `ambiguous` until a dry run can inspect the
actual progress rows:

- if a row contains a stored word/surface, resolve it from that evidence;
- if its timestamps prove it predates or postdates the colliding deck release,
  offer the inferred mapping with `reconstructed` provenance for approval;
- if neither exists, retain the row under its legacy key and report it for a
  manual choice;
- never duplicate one ambiguous progress row onto both surfaces.

At worst this requires two user decisions, not a compromise across the whole
Spanish deck.

## Cross-language consequence

The alias registry is shared infrastructure, not a Spanish compatibility
branch. French, Dutch, Portuguese and Artist mode can register earlier IDs,
retired cards or imported deck IDs through the same schema. A language adapter
normalizes a surface; it does not implement progress migration.

## Decision requested

Approve this direction:

- Fluency Next's long `card_<language>_...` ID remains canonical;
- all historical Spanish IDs become flat aliases resolved by observed surface;
- duplicate lemma-era cards collapse to one surface card;
- clitic aliases resolve to their own surface rather than the old merged base;
- the two reused six-hex IDs remain explicitly ambiguous pending the later
  progress dry run;
- no Google Sheet rows are rewritten during the data migration.

After approval, the next implementation unit is the shared alias-registry
schema, validator and deterministic Spanish crosswalk generator. It will emit
a report before any preserved sentence or embedding asset is copied.

## Implemented result

Approved and implemented on 2026-08-22. Fluency Next now has:

- a language-agnostic, non-recursive progress-alias registry and JSON schema;
- content-hashed source records referenced by compact evidence IDs;
- an explicit Spanish surface normalizer that preserves accents and inflected
  surface identity;
- a deterministic crosswalk generator and `fluency identity crosswalk` CLI;
- atomic, immutable workspace output with hashes for cards, aliases,
  exceptions and the audit report;
- tests for duplicate collapse, clitic-surface identity, cyclic legacy maps,
  collision ambiguity, invalid registries and Spanish normalization.

The real output is:

```text
/Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/
  migrations/es/speech/es-speech-surface-crosswalk-v1/
```

Measured result:

- 9,999 canonical active surface cards;
- 27,403 resolved historical Speech progress aliases;
- six ambiguous aliases across the two known collision components;
- zero unresolved aliases;
- zero source-file, Google Sheets or active-release mutations.

The six exception records are the two IDs directly observed with different
surfaces plus four unobserved intermediate IDs connected to those collision
components. They remain explicit until the later real-progress dry run. No
crosswalk output is used as a release or inventory source.
