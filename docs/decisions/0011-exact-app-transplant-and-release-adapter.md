# Decision 0011: exact app transplant with a clean release adapter

## Status

Accepted and implemented on 2026-08-22. This supersedes the compact browser
runtime described in Decisions 0007 and 0009; their release and data-contract
decisions remain valid.

## Decision

The current Fluency application surface is transplanted as the working product
baseline: its HTML, CSS, JavaScript modules, welcome and setup flows, active
card experience, numbered scrubber, scoring, resume, and completion behaviour
remain intact. The earlier pilot runtime is removed from `app/` and retained
only as `docs/reference/pilot-ui-v1.html` for later design reference.

The clean repository does not copy `Data/` or `Artists/` from the historical
repository. Instead, every immutable Speech release emits a narrow compatibility
pair:

```text
app/vocabulary.index.json
app/vocabulary.examples.json
```

The local server maps the existing app URLs, such as
`/Data/French/vocabulary.index.json`, to those files in the one manually active
release. Their hashes are part of the release manifest. Missing or invalid
active-release metadata fails closed; no old directory is searched and no
other run is used as fallback.

The service worker never caches these mutable alias URLs. Activating a release
therefore cannot leave a previous deck or example file hidden under the same
URL. Offline support for release data must later use immutable, release-scoped
URLs.

## Surface-only rule

The compatibility renderer does not emit `lemma` or
`most_frequent_lemma_instance`. The existing Merge Lemmas control is hidden
when that capability is absent. Stable identity remains the complete
`surface_card_id`; the shorter legacy-shaped ID exists only at the old app
boundary and is deterministically derived from it.

## Consequences and deliberate deferrals

- App parity is obtained before frontend refactoring; the copied runtime is not
  yet the hoped-for smaller final implementation.
- Pipeline and release cleanup proceed independently of the UI implementation.
- Release-aware diagnostics and release-frozen session resume from the compact
  prototype must be reintroduced behind the exact app, without redesigning its
  visible flow.
- Artist mode remains present in the product surface but has no clean data
  source until its own release adapter is implemented.
