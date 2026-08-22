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
  navigation, and isolated local progress.
- A release pill in the top bar. It opens the exact candidate, deck and
  composition hashes, layer source/artifact IDs, fallback policy, and explicit
  WSD omission.
- The active-study gear opens card direction, automatic speech, progress, Card
  Data, and release audit. Card Data uses its numbered example scrubber; the
  `bonjour` fixture card has three examples for verification.
- Learn contains only unseen cards in the selected stable set. Review is a
  separate level-wide queue. Leaving a session preserves the exact release,
  card order, position, side, direction, speech setting, and example position;
  reload the page to verify the original resume prompt.
- Completion preserves the existing app actions: automatic next-unseen-set
  continuation for Learn, Main menu, and Redo set. No new completion action is
  introduced by this migration.

The old Fluency JavaScript and data loaders are not running. The new compact
runtime binds the immutable release to the original product shell.

## Release control

```bash
PYTHONPATH=src python3.12 -m fluency release list --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace
PYTHONPATH=src python3.12 -m fluency release validate fr-speech-pilot-0004 --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace
PYTHONPATH=src python3.12 -m fluency release activate fr-speech-pilot-0004 --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace
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

The first pilot UI is preserved at `docs/reference/pilot-ui-v1.html` and as Git
tag `pilot-ui-v1`; it is not the production app entry point.

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
unpinned WSD models. The WSD architecture is fixed to embedding retrieval plus
a language-specific reranker; the exact French model revisions are intentionally
unselected until that decision is reviewed.
