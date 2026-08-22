# Decision 0007 — Exact release composition and the original product shell

## Status

Accepted and implemented on 2026-08-22.

## Decision

The rebuilt runtime uses the current Fluency `index.html` and visual CSS as its
product shell. It does not load the legacy JavaScript graph. A compact adapter
binds the new French Speech release to the existing setup, card, scrubber,
keyboard, authentication-welcome, and modal surfaces.

The first pilot interface remains available in two deliberate forms:

- Git tag `pilot-ui-v1`, which preserves the complete runnable repository state.
- `docs/reference/pilot-ui-v1.html`, which keeps the HTML readable for later
  design comparison and selective reuse.

Every app-selectable deck is now an immutable release with three files:

```text
releases/<language>/<mode>/<release-id>/
├── composition.json
├── manifest.json
└── deck.json
```

`composition.json` selects each layer by exact source ID and content-addressed
artifact ID. Layer dependencies name the upstream artifact IDs they require.
Incompatible selections fail validation. Conflict policy is `error`; fallback
is `none` unless a layer explicitly declares a `missing_only` fallback and the
composition opts into `explicit_missing_only`.

`catalog.json` is the only list the app may select from. Direct query selection
uses `?release=<release-id>` but still requires the release to be catalogued.
`active.json` chooses the default candidate. The browser verifies deck and
composition SHA-256 hashes against the manifest before rendering.

## Consequences

- An old run cannot silently contribute records to a new release.
- WSD can be absent, replaced, or added later without blocking the app; its
  exact omission or selected source is visible in the release audit.
- Composing a candidate never activates it. Validation and activation are
  separate commands.
- The copied CSS is intentionally retained for exact visual parity first. It
  can be pruned incrementally with browser snapshots once each retained product
  surface is covered, without changing the release contracts.
