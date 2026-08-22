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
contracts, French tokenization boundary, exact release composition, and the
transplanted Fluency application running a 25-card French Speech pilot are
implemented. The old app's split French data URLs resolve only to files
generated inside the manually active immutable release, and those aliases are
never service-worker cached. The first fresh French audit profile is locked to
200 surface cards and three examples per card. Its language-agnostic harvester
uses shared Speech rules plus French and source adapters, reads only run-owned
surface inventories, and supports explicit Tatoeba or aligned OpenSubtitles
snapshots without fallback. Its Wiktionary-ready sense-menu boundary normalizes
dictionary data without making lemmas card identities. The profile creates six
inspectable stage folders without loading historical deck data, installing
model packages, executing WSD, or activating a release. A complete assignment
bundle produced by a separate WSD task can now be validated and published into
immutable Stage 04 without stale-run mixing or method coupling. French WSD
results, final selection, release diagnostics in the transplanted UI, Spanish
migration, Artist mode, and production integration are not complete.

See `docs/runbooks/local-speech-pilot.md` for the exact local test flow.
The agreed long-running migration sequence and operating rules are recorded in
`docs/ROADMAP.md`.
