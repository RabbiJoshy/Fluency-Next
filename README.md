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
make dev
```

The development server listens on <http://127.0.0.1:4173> by default. It uses
only the local `app/` directory and has no production or GitHub dependency.

## Current scope

Only the repository bootstrap exists. No language pipeline, corpus ingestion,
WSD, migration, release, or production integration has been implemented yet.

