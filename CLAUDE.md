# Fluency Next — AI reference

Local-first successor to Fluency. Python pipeline plus a transplanted vanilla-JS
app. Large corpora, model caches and generated releases live in a separate
`Fluency-Workspace`, never here.

## Read first

**`docs/INVARIANTS.md`** — the five rules that constrain every change. Read it
before altering architecture, contracts or provenance. In brief:

1. Migrate the shape, preserve the substance, label both.
2. Absence is declared, never inferred.
3. A run must not record what it did not verify.
4. Adapters absorb irregularity at the edges; the engine exists once.
5. A language or mode is added by creating files, not by editing lists.

Then `docs/ROADMAP.md` for the migration plan and `docs/decisions/` for why
particular things are the way they are.

## Shape

```
src/fluency/
  cli/            one module per command group, behind a registry
  core/           workspace, hashing, io, language naming
  languages/      one package per language; each declares LANGUAGE_CODE
  inventory/      4 frequency adapters -> surface-inventory/v1
  sense_menu/     kaikki + spanishdict  -> sense-menu/v1
  harvest/        tatoeba + opensubtitles -> parallel-sentence/v1, and pools
  features/       provider-neutral sense features (NOT under wsd/)
  menus.py        sense-menu contract    (NOT under wsd/)
  projections.py  release-facing view    (NOT under wsd/)
  nlp/            pinned POS model, resumable embedding store, model registry
  wsd/            the classifier; optional enrichment, runs two stages late
  release/        composition, validation, activation
config/           policies per language, mode, provider and model
```

The three files marked *NOT under wsd/* are there deliberately: a menu or a
release must be buildable without the classifier importing. A test enforces it.

## Stage graph

`STAGE_INPUTS` in `pipeline/planning.py` is authoritative. It is a **diamond,
not a chain** — `sense_menu` and `sentence_harvest` are siblings, both reading
only the inventory. Changing a dictionary snapshot costs no corpus re-scan.
Use `stages_invalidated_by()` rather than reasoning from the stage numbering.

## Working with Josh

- **Verify before recommending.** Read the file rather than the label. Repeated
  mistakes here came from reading a name (`retained_materialized_assignments`,
  a `SPACY_POS_MODEL` constant, one assignment record) and generalising.
  Measure the distribution; it is usually one command away.
- **Long runs belong in the background.** Corpus scans, embeddings and model
  downloads take minutes; print progress rather than blocking.
- **Spend is gated.** Anything calling a paid model reports its projected units
  before running. Note the guard currently reads the harvest cap rather than the
  sampling cap and over-estimates about sixfold.
- **Name pipeline steps by file and purpose**, not by number.
- **Concurrent sessions are normal.** Check `git status` before committing and
  commit only your own paths.

## Commands

```bash
make test                       # unittest, currently 422
PYTHONPATH=src python -m fluency pipeline plan --profile config/pipelines/<lang>/speech/<profile>.json
PYTHONPATH=src python -m fluency pipeline inventory|sense-menu|harvest|wsd-import|build-run-release
PYTHONPATH=src python -m fluency pools list --language <lang>
PYTHONPATH=src python -m fluency release list|validate|activate --language <lang>
```

`--language` defaults to `fr` on every pipeline subcommand. Passing the wrong one
fails loudly, but it is an easy omission.
