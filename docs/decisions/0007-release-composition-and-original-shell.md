# Decision 0007 — Exact release composition and the original product shell

## Status

Accepted on 2026-08-22. The compact-runtime portion was superseded by Decision
0011; the release-composition contract remains active.

## Decision

The first implementation used the current Fluency `index.html` and visual CSS
with a compact JavaScript runtime. Decision 0011 later replaced that runtime
with an exact application transplant and a release-to-split-data adapter.

The first pilot interface remains available in two deliberate forms:

- Git tag `pilot-ui-v1`, which preserves the complete runnable repository state.
- `docs/reference/pilot-ui-v1.html`, which keeps the HTML readable for later
  design comparison and selective reuse.

Every app-selectable deck is an immutable release whose canonical files are:

```text
releases/<language>/<mode>/<release-id>/
├── composition.json
├── manifest.json
├── deck.json
└── app/
    ├── vocabulary.index.json
    └── vocabulary.examples.json
```

`composition.json` selects each layer by exact source ID and content-addressed
artifact ID. Layer dependencies name the upstream artifact IDs they require.
Incompatible selections fail validation. Conflict policy is `error`; fallback
is `none` unless a layer explicitly declares a `missing_only` fallback and the
composition opts into `explicit_missing_only`.

`active.json` chooses the release served through the existing app's data URLs.
The server resolves only the app assets named and hashed by that release's
manifest. Catalogued candidate selection and in-app release auditing from the
compact runtime are deferred for restoration behind the transplanted app.

## Consequences

- An old run cannot silently contribute records to a new release.
- WSD can be absent, replaced, or added later without blocking the app; its
  exact omission or selected source is visible in the release audit.
- Composing a candidate never activates it. Validation and activation are
  separate commands.
- The copied CSS is intentionally retained for exact visual parity first. It
  can be pruned incrementally with browser snapshots once each retained product
  surface is covered, without changing the release contracts.
