# Local French Speech pilot runbook

## First run

Open one terminal and run:

```bash
cd /Users/joshuathomasamar/PycharmProjects/Fluency-Next
make test
make pilot
make dev
```

Then open <http://127.0.0.1:4173>.

`make pilot` is deterministic and normally finishes immediately. Re-running it
is safe when the release content is unchanged. An existing release with
different bytes is rejected rather than overwritten.

## What should be visible

- The recognisable Fluency welcome, setup, language, level, set, and study
  surfaces.
- A clear French pipeline pilot notice.
- 25 French surface-form cards.
- Card reveal, meaning selection, examples, lookup, and direction controls.
- French browser speech using locale `fr-FR`, when the browser supports speech
  synthesis.
- Correct/review recording, card navigation, summary counts, and an explicit
  two-step reset.
- Release diagnostics stating that WSD is not connected and pilot progress is
  isolated.

Progress survives a browser reload on that local origin. It does not read or
write the old Fluency app's progress.

To preview one immutable candidate without changing `active.json`, open:

```text
http://127.0.0.1:4173/?release=fr-speech-pilot-0001
```

If that exact release does not exist, the app shows an error. It never silently
falls back to another release.

## Data path

The pilot builder writes only:

```text
/Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/releases/fr/speech/
```

The server exposes that folder under `/releases/`. It serves the application
from `Fluency-Next/app/` and does not point the old application's HTML at the new
data.

To use a different workspace for one command:

```bash
make pilot FLUENCY_WORKSPACE=/absolute/path/to/workspace
make dev FLUENCY_WORKSPACE=/absolute/path/to/workspace
```

## Troubleshooting

If the app reports that the active pointer is unavailable, stop the server and
run `make pilot`, then start `make dev` again. Diagnose the workspace with:

```bash
PYTHONPATH=src python3.12 -m fluency workspace doctor \
  --path /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace
```

Do not manually edit files inside the immutable release directory. Change the
checked-in fixture or the release builder, choose a new release ID, validate,
and publish a new release instead.
