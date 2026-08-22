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
Preserved releases created before the study-structure contract are exposed
through a labelled, runtime-only single-set adapter; their immutable files are
not rewritten.

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
