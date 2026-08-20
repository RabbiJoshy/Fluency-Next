# Local workspace runbook

## Initialize

```bash
cd /Users/joshuathomasamar/PycharmProjects/Fluency-Next
PYTHONPATH=src python3.12 -m fluency workspace init \
  --path /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace
```

Initialization is idempotent. It refuses a non-empty directory that does not
already contain a valid Fluency workspace marker.

## Inspect

```bash
PYTHONPATH=src python3.12 -m fluency workspace show \
  --path /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace
```

## Diagnose

```bash
PYTHONPATH=src python3.12 -m fluency workspace doctor \
  --path /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace
```

The doctor checks the marker, directory layout, access, atomic-promotion
filesystem, and separation from the code repository. It does not download,
modify, or delete pipeline data.

## Storage rules

- Never edit a raw snapshot after import.
- Never edit an object directory or completed run manifest.
- Treat cache contents as reproducible and disposable.
- Do not manually remove referenced objects.
- Garbage collection will default to a dry run and quarantine before deletion.

