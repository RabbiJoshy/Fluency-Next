# Fluency Next

Fluency Next is the local-first successor to Fluency. French Speech is the first
implementation, while the core is designed to support additional languages and
modes without duplicating vocabulary identities or pipeline logic.

The code repository contains source code, configuration, tests, documentation,
and compact release metadata. Large corpora, model caches, intermediate runs,
registries, and generated releases belong in the separate `Fluency-Workspace`.

## Local bootstrap

Python 3.12 is the supported development runtime for the initial rebuild.

```bash
make bootstrap
make test
make pilot
make dev
```

The development server listens on <http://127.0.0.1:4173> by default. It uses
the local `app/` directory and mounts only compact releases from the separate
workspace. It has no production or GitHub dependency.

## Current scope

The stable surface-card identity, external workspace, immutable artifact/run
contracts, French tokenization boundary, and a recognisable Fluency application
running a 25-card French Speech pilot are implemented. The pilot is curated
fixture data: corpus ingestion, frequency ranking, embeddings, WSD, calibration,
Spanish migration, Artist mode, and production integration have not been
implemented yet.

See `docs/runbooks/local-speech-pilot.md` for the exact local test flow.
