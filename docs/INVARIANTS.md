# Invariants

Rules that outlive any particular plan. `ROADMAP.md` describes a migration that
will finish; the decisions in `decisions/` record particular choices. These
constrain both, and a change that breaks one of them is wrong even when it is
convenient.

Each is stated with the failure it prevents, because a rule without its reason
gets discarded by whoever finds it inconvenient.

---

## 1. Migrate the shape, preserve the substance, label both

A contract change must not strand data that is still good, and a converted
artifact must never be mistakable for a natively produced one -- in either
direction.

Three obligations:

- **Do not break call sites.** A relocated module leaves a re-export at the old
  path. `wsd/menus.py`, `wsd/features.py`, `wsd/projection.py` and
  `release/io.py` are all shims for this reason.
- **Do not strand data.** Old artifacts are bridged into the new contract rather
  than discarded. `artist/wsd_bridge.py` lifts flattened Artist assignments into
  the v7 dual view.
- **Do not blur the two.** Contract, method and carriage are separate declared
  fields.

The third exists because of a real misreading. `source_kind:
retained_materialized_assignments` describes how decisions were *carried
forward*; it was read as what *computed* them, and the Rosalia releases were
briefly believed to be stranded on v5. They were not: `assignment_method` said
`spanishdict-embed-v7-provider` for all 4,919 decisions. Over-trusting migrated
data and under-trusting native data are both possible, and the second nearly
caused correct work to be re-run.

Recorded in `config/wsd/modes.json` (method vs contract) and measured per
release by `wsd/provenance.py`.

## 2. Absence is declared, never inferred

An optional thing that a language, mode or provider does not have is emitted as
an explicit empty value, not omitted. A caller must never have to distinguish
"this does not apply" from "nobody filled it in".

`config/sense_menu/languages/fr-v1.json` carries `region_tags: []` with a note
saying it is declared and empty pending a French list. An unmapped POS tag
returns an empty set meaning *no evidence*, never *reject everything* -- reading
those two the same way is what deletes every sense on the commonest words.

## 3. A run must not record what it did not verify

Provenance that can be wrong is worse than provenance that is missing, because
nothing downstream has reason to doubt it.

Lyrics recorded `es_dep_news_trf@3.8.0` in every run manifest while loading the
model unchecked; the claim held only because that version happened to be
installed. The same module named its embedding model as a literal in the same
manifest. Both now read `config/nlp/models.json`, and `nlp/pos.load_pinned`
refuses a model whose revision does not match the pin.

## 4. Adapters absorb irregularity at the edges; the engine exists once

Everything that varies by language, mode or provider is data behind an adapter.
Everything that does not exists exactly once.

Nine adapters cover frequency lists, dictionaries and corpora. Below them the
contracts are neutral and the engine is shared: `surface-inventory/v1`,
`sense-menu/v1`, `parallel-sentence/v1`, then one WSD, one selection, one release
path. Adding Portuguese cost one language package and config entries; it required
no new stage and no branch in the engine.

Corollary: a contract lives outside the package that consumes it. A sense menu or
a release must be buildable without the classifier importing, and a test asserts
exactly that by blocking `fluency.wsd` and building both.

## 5. A language or mode is added by creating files, not by editing lists

Discovery over registration. A hardcoded list is a file every concurrent session
must edit, and therefore a guaranteed conflict.

Language packages declare their own `LANGUAGE_CODE` and are discovered;
per-language display data lives in app config; command groups register
themselves. Adding a language previously meant editing eight registries.

---

## Applying these

When a change seems to require breaking one, that is usually a sign the change
is shaped wrongly rather than that the invariant is. The exception is a
deliberate, recorded decision in `decisions/` that says which invariant it
breaks and why -- which is itself an application of rule 1.
