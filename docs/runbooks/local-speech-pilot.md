# Local French Speech pilot runbook

## First run

```bash
cd /Users/joshuathomasamar/PycharmProjects/Fluency-Next
make test
make pilot
make dev
```

Open <http://127.0.0.1:4173/>. `make pilot` deterministically composes and
activates the curated release. Re-running it is safe when the bytes are
unchanged; an existing release with different bytes is rejected.

## What should be visible

- The original Fluency welcome, setup, level, set, card, scrubber, and keyboard
  surfaces.
- A 25-card French surface-form deck with meanings, examples, speech, scoring,
  navigation, and the existing app's local progress behaviour. The `bonjour`
  fixture card has three examples for verification.
- No Merge Lemmas choice for the surface-only release.
- Learn contains only unseen cards in the selected stable set. Review is a
  separate level-wide queue. Leaving a session preserves the existing app's
  queue and offers its original resume prompt after reload.
- Completion preserves the existing app actions: automatic next-unseen-set
  continuation for Learn, Main menu, and Redo set. No new completion action is
  introduced by this migration.

The transplanted Fluency JavaScript is the runtime. Its existing French split
data URLs are server-side aliases to compatibility files generated inside the
one active immutable release. No historical `Data/` or `Artists/` directory is
present in this repository.

## Release control

```bash
PYTHONPATH=src python3.12 -m fluency release list --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace
PYTHONPATH=src python3.12 -m fluency release validate fr-speech-pilot-0005 --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace
PYTHONPATH=src python3.12 -m fluency release activate fr-speech-pilot-0005 --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace
```

To preview a non-active approved candidate, use
`?release=<catalogued-release-id>`. Unknown and uncatalogued IDs fail closed;
the app never substitutes the active release or fills gaps from another deck.
Releases created before the study-structure contract are unsupported. Every
candidate must validate against the current contract; no runtime adapter fills
in missing structure or data.

Generic composition takes an already assembled compact deck plus a reviewed
composition document and does not activate the result:

```bash
PYTHONPATH=src python3.12 -m fluency release compose \
  --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace \
  --composition /absolute/path/to/composition.json \
  --deck /absolute/path/to/deck.json
```

## Data path and safety

Generated releases live only under:

```text
/Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/releases/<language>/<mode>/
```

The server mounts this read-only at `/releases/`. Do not manually edit an
immutable release. Create a new release ID, validate it, inspect it as a
candidate, and activate it deliberately.

The first pilot UI is preserved at `docs/reference/pilot-ui-v1.html`; it is not
the production app entry point.

## Fresh French 200 × 3 audit skeleton

Create an inspectable run skeleton without downloading sources, loading a
model, harvesting sentences, or running WSD:

```bash
PYTHONPATH=src python3.12 -m fluency pipeline plan \
  --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace \
  --profile config/pipelines/fr/speech/audit-200x3.json
```

The resulting folder is deliberately readable:

```text
runs/fr/speech/<run-id>/
├── manifest.json
├── profile.json
├── plan.json
└── stages/
    ├── 01_inventory/contract.json
    ├── 02_sense_menu/contract.json
    ├── 03_sentence_harvest/contract.json
    ├── 04_wsd_assignments/contract.json
    ├── 05_example_selection/contract.json
    └── 06_release_build/contract.json
```

All contracts begin as `pending`. The profile blocks lemma identity, legacy
inputs, cross-run fallbacks, example shortfalls, automatic activation, and
unpinned WSD models. The WSD architecture is the language-adapted closed-menu
stack: gloss retrieval, an optional language-specific tuple reranker,
path-specific calibration, optional aligned-English correction, and explicit
disposition. The exact French model revisions are intentionally unselected until
that decision is reviewed.

The French sense-menu stage is a replaceable adapter boundary. The current
profile is ready for `wiktionary-sense-menu/v1`; it must write normalized
`sense-menu/v1` records joined by `surface_card_id`. Lemmas may be retained as
dictionary lookup metadata but can never become card identity. A different
dictionary provider can replace this adapter without changing harvesting, WSD,
selection, release composition, or the app contract.

The pinned source edition is **English Wiktionary**, with French target entries
and English glosses. Do not substitute the French Wiktionary edition: its gloss
language is French, so it is a different WSD input. Kaikki's current
language-specific postprocessed download is suitable for the bounded audit even
though Kaikki marks that distribution route as deprecated; the adapter consumes
the documented Wiktextract fields and is not coupled to Kaikki's website layout.

## Expensive-stage handoff

Harvesting and WSD are intentionally not run by the assistant. At each approved
stage, the assistant supplies an exact local command with pinned configuration
and the expected output folder. Run that command in this repository, then let
the assistant inspect counts, schemas, hashes, source evidence, shortfalls, and
model pins before the next stage. A command never activates a release; release
composition, validation, visual audit, and activation remain separate gates.

## Fresh surface-inventory command

French Speech ranking uses Lexique 4.00's `FreqOrtho`: an orthographic surface
frequency from its 316-million-word subtitle corpus. The adapter deliberately
does not ingest Lexique lemma, POS, or inflection fields. Reviewed exclusions
come from `config/inventory/languages/fr-v1.json`; they are removed without
normalization or redirect and remain visible in the stage report. Download the
pinned source into the external workspace:

```bash
mkdir -p /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/raw/frequency/lexique-4.00-2026-02-10

curl --fail --location --continue-at - \
  https://lexique.org/databases/Lexique400/Lexique400.tsv \
  --output /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/raw/frequency/lexique-4.00-2026-02-10/Lexique400.tsv
```

Create a new skeleton with the current profile, then use the run ID printed by
that command to build stage 01:

```bash
PYTHONPATH=src python3.12 -m fluency pipeline plan \
  --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace \
  --profile config/pipelines/fr/speech/audit-200x3.json

PYTHONPATH=src python3.12 -m fluency pipeline inventory \
  --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace \
  --run-id <new-run-id> \
  --snapshot /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/raw/frequency/lexique-4.00-2026-02-10/Lexique400.tsv \
  --snapshot-id lexique-4.00-2026-02-10
```

Inspect `inventory.json`, `frequency-ranks.json`, `report.json`, and
`manifest.json` under the new run's `stages/01_inventory/output/`. The adapter
rejects snapshots outside `workspace/raw`, an existing stage output, a schema
mismatch, or fewer surfaces than the profile requires.

## Wiktionary snapshot and sense-menu command (after inventory approval)

The current English-Wiktionary French snapshot is large enough to download
locally. It is append-only inside the external workspace:

```bash
mkdir -p /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/raw/wiktionary/enwiktionary-2026-08-05

curl --fail --location --continue-at - \
  https://kaikki.org/dictionary/French/kaikki.org-dictionary-French.jsonl \
  --output /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/raw/wiktionary/enwiktionary-2026-08-05/kaikki.org-dictionary-French.jsonl
```

Once the approved run has `stages/01_inventory/output/inventory.json`, normalize
that exact snapshot into the run-owned menu:

```bash
PYTHONPATH=src python3.12 -m fluency pipeline sense-menu \
  --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace \
  --run-id <approved-run-id> \
  --snapshot /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/raw/wiktionary/enwiktionary-2026-08-05/kaikki.org-dictionary-French.jsonl \
  --snapshot-id enwiktionary-2026-08-05
```

The result is written once under
`runs/fr/speech/<run-id>/stages/02_sense_menu/output/`. Inspect
`sense-menu.json`, `report.json`, and `manifest.json`. The report exposes every
surface's analysis/sense count and every `no_menu`; rerunning against the same
run is rejected rather than overwriting it.

## Official Tatoeba snapshot and sentence harvest

The Tatoeba adapter consumes the official weekly detailed French and English
sentence exports plus their direct link export. It does not consume a
ManyThings ZIP. Download the three files and create their pinned manifest in
one operation (change the retrieval date when taking a later snapshot):

```bash
cd /Users/joshuathomasamar/PycharmProjects/Fluency-Next
python3.12 scripts/fetch_tatoeba_snapshot.py \
  --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace \
  --snapshot-id tatoeba-weekly-retrieved-2026-08-22-fr-en \
  --language fr \
  --translation-language en
```

The harvester deliberately requires the same run's
`stages/01_inventory/output/inventory.json` and `frequency-ranks.json`. After
the download completes, run:

```bash
PYTHONPATH=src python3.12 -m fluency pipeline harvest \
  --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace \
  --run-id <approved-run-id> \
  --source tatoeba=/Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/raw/tatoeba/fr-en/tatoeba-weekly-retrieved-2026-08-22-fr-en
```

The result is written once under
`runs/fr/speech/<run-id>/stages/03_sentence_harvest/output/`. Inspect
`report.json`, `candidates.json`, `sentence-bank.jsonl`, and `manifest.json`.
Running the command again against that run is rejected rather than merging or
overwriting candidates.

## External WSD handoff

WSD method selection and evaluation happen in the separate WSD task. Fluency
Next expects that work to produce one complete JSON bundle conforming to
`schemas/wsd-assignment-bundle.schema.json`. Put the finished file below:

```text
/Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/raw/wsd/<method-or-run>/bundle.json
```

The bundle must cover every harvested candidate explicitly and pin the content
IDs of this run's inventory, sense menu, candidate index, and sentence bank.
Once the external task has produced it, the import itself is a quick local
validation/publication command and does not run any models:

```bash
cd /Users/joshuathomasamar/PycharmProjects/Fluency-Next
PYTHONPATH=src python3.12 -m fluency pipeline wsd-import \
  --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace \
  --run-id <approved-run-id> \
  --bundle /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/raw/wsd/<method-or-run>/bundle.json
```

Successful import writes `stages/04_wsd_assignments/output/` exactly once. It
does not select final examples, build a release, or activate one.

An OpenSubtitles-only profile uses `sources: ["opensubtitles"]` and passes an
aligned snapshot directory instead. That directory contains
`OpenSubtitles.en-fr.fr`, `OpenSubtitles.en-fr.en`,
`OpenSubtitles.en-fr.ids`, and a `snapshot.json` with version
`opensubtitles-aligned-snapshot/v1`, language pair, snapshot ID, license,
attribution, and source URL. The command then changes only its explicit source:

```bash
--source opensubtitles=/Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/raw/opensubtitles/en-fr/<snapshot-id>
```
