# Fluency Next — AI reference

Local-first successor to Fluency. Python pipeline plus a transplanted vanilla-JS
app (`app/`, no framework or build step). Python 3.12; `.venv` is a symlink to
the old repository's virtualenv.

**Two roots.** Code, config, tests and compact release metadata live here. Large
corpora, model caches, runs, pools and generated releases live in
`../Fluency-Workspace` and never in git. `../Fluency` is the older repository,
still the live app; treat it as reference, not a target.

## Read first

**`docs/INVARIANTS.md`** — the five rules that constrain every change. Read
before altering architecture, contracts or provenance.

1. Migrate the shape, preserve the substance, label both.
2. Absence is declared, never inferred.
3. A run must not record what it did not verify.
4. Adapters absorb irregularity at the edges; the engine exists once.
5. A language or mode is added by creating files, not by editing lists.

Then `docs/ROADMAP.md` for the plan and `docs/decisions/` for why things are as
they are. `docs/reference/` holds WSD measurements carried over from the older
repository — read its README first, because those were taken on Spanish against
a SpanishDict menu and not all of them transfer.

## Words to use precisely

`docs/NOMENCLATURE.md` pins the vocabulary. The one that matters most:
**provider** means a *sense-menu source* — SpanishDict, Wiktionary — not a
language and not a corpus. SpanishDict serves one language; Wiktionary serves
French, Portuguese and everything after. **Provider parity** is the requirement
that a concept built for one provider ships with the other's equivalent.

Ask "is this provider-agnostic?" rather than "does this work for other
languages?" — the second hides which you meant.

It also names the app's parts (setup flow, study view, card faces, pills,
modals) and the four words that mean different things on screen and in the data:
`tag`, `context`, `source`, `level`.

## The load-bearing fact

**A card's identity is the observed surface form.** `card_id = f(language,
surface_key)` and nothing else — not the lemma, not a sense, not a rank.
Everything else is metadata hanging off it. Lemmas may be lookup or linguistic
detail; making one an identity breaks learner progress, and the surface-inventory
schema has no field for one.

## Shape

```
src/fluency/
  cli/            one module per command group, behind a registry
  core/           workspace, hashing, io, language naming
  languages/      one package per language; each declares LANGUAGE_CODE
  inventory/      4 frequency adapters   -> surface-inventory/v1
  sense_menu/     kaikki + spanishdict   -> sense-menu/v1
  harvest/        tatoeba + opensubtitles -> parallel-sentence/v1, and pools
  features/       provider-neutral sense features   (NOT under wsd/)
  menus.py        sense-menu contract                (NOT under wsd/)
  projections.py  release-facing view                (NOT under wsd/)
  nlp/            pinned POS model, resumable embedding store, model registry
  wsd/            the classifier: optional enrichment, runs two stages late
  release/        composition, validation, activation
config/           policies per language, mode, provider and model
```

The three marked *NOT under wsd/* are placed deliberately: a menu or a release
must build without the classifier importing. A test enforces it by blocking
`fluency.wsd` entirely and importing both.

## Pipeline

```
01 inventory → 02 sense_menu ┐
             → 03 harvest    ┴→ 04 wsd → 05 selection → 06 release
```

`STAGE_INPUTS` in `pipeline/planning.py` is authoritative and it is a **diamond,
not a chain**: `sense_menu` and `sentence_harvest` are siblings, both reading only
the inventory. Changing a dictionary snapshot costs no corpus re-scan. Use
`stages_invalidated_by()`; do not reason from the numbering.

**Stages are immutable.** A stage with output refuses to be rebuilt — create a
new run instead. Run ids are `<timestamp>-<8 lowercase hex>`; `pt` or `00pt0001`
are rejected because they are not hex.

**WSD is optional.** A deck ships with every example marked explicitly
unassigned rather than blocking. Portuguese and Spanish both have such releases.

Languages with profiles: `es`, `fr`, `pt`. Modes: speech, lyrics, artist.

## Working with Josh

- **Verify before recommending.** Read the file, not the label. Repeated errors
  here came from trusting a name (`retained_materialized_assignments`), a
  constant (`SPACY_POS_MODEL`), or a single record (axis margins) and
  generalising. The distribution is usually one command away — measure it.
- **Long runs go in the background.** Corpus scans, embeddings and model
  downloads take minutes.
- **Spend is gated.** Anything calling a paid model prints projected units first.
  Known defect: the guard reads the harvest cap rather than the sampling cap and
  over-estimates roughly sixfold.
- **Name pipeline steps by file and purpose**, never by number alone.
- **Concurrent sessions are normal.** Check `git status` before committing;
  commit only your own paths. Others' uncommitted work is routinely present.
- **Don't rebuild what a pool already holds.** Named, described sentence pools
  live in `<workspace>/pools/<lang>/`; `fluency pools list` shows them.

## Commands

```bash
make test        # unittest discovery, currently 422
PYTHONPATH=src python -m fluency pipeline plan --profile config/pipelines/<lang>/speech/<profile>.json
PYTHONPATH=src python -m fluency pipeline inventory|sense-menu|harvest|wsd-import|build-run-release
PYTHONPATH=src python -m fluency pools list --language <lang>
PYTHONPATH=src python -m fluency release list|validate|activate --language <lang>
PYTHONPATH=src python -m fluency.speech.wsd_execute --run-dir <run> --out <bundle.json> --profile-id <id>
```

Every pipeline subcommand takes `--workspace`, and **`--language` defaults to
`fr`** — an easy omission that fails loudly but confusingly.

WSD writes a *bundle*; `pipeline wsd-import` publishes it into stage 04. The
release builder reads `stages/04_wsd_assignments/output/assignments.jsonl`, not
the bundle, so the import step is not optional.
