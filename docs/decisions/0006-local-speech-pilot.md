# 0006: Local French Speech pilot and compact release boundary

- Status: Accepted
- Date: 2026-08-20

## Decision

Build the first visible French Speech deck inside a compact, product-parity
reimplementation of the Fluency shell in `Fluency-Next/app`. The old Fluency
HTML, JavaScript, data files, progress, and service worker are used as a visual
and behavioural reference but are not loaded or modified by the rebuilt app.

The app consumes only a compact release contract from the external workspace:

```text
releases/fr/speech/
├── active.json
└── fr-speech-pilot-0001/
    ├── manifest.json
    └── deck.json
```

`active.json` selects an immutable release manifest. The manifest identifies and
hashes the deck. The local server mounts workspace `releases/` at the read-only
same-origin URL `/releases/`; it does not expose raw inputs, registries, model
caches, or pipeline runs.

The pilot deck is deterministically built from 25 checked-in, manually curated
fixture cards. Fixture sense and example IDs are visibly namespaced and must not
be treated as production registry identities. Validation rejects frequency,
coverage, corpus-count, or percentage claims. The manifest explicitly records
that WSD is disabled and not connected.

Browser progress is stored under the release-declared namespace and the
language/mode pair. Its records preserve the existing useful shape—correct/wrong
counts, last timestamps, and SRS stage—but cannot collide with legacy or future
production progress.

An optional `?release=<release-id>` parameter selects one immutable local
candidate explicitly. If it is absent, the app follows `active.json`. A missing
explicit candidate fails closed and never falls back to the active or an older
release.

## Mode and language boundary

Release locations are partitioned by language and mode. A future French Artist
release therefore belongs under `releases/fr/artist/`, while another language's
Speech release belongs under its own language key. Stable surface card IDs stay
shared across modes; mode-specific payload and progress do not.

The validators and JSON schemas in this gate are intentionally strict for the
French Speech pilot. We will generalize the release envelope only when the first
production release or second mode gives us real shared requirements, rather
than guessing them now.

## Consequences

- The recognisable setup and study journey plus the complete release-to-browser
  path can be exercised before corpus and WSD choices are settled.
- Replacing fixture content later requires publishing a new release, not
  changing the browser's loading path.
- The pilot is a functional and integration test, not evidence of vocabulary
  coverage or pipeline quality.
- There is no service worker, remote backend, authentication, deployment, or
  connection to the old app in this gate.
