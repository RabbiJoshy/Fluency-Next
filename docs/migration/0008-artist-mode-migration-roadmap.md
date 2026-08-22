# Artist/Lyrics mode migration

## Outcome

Artist mode is migrated as a product-parity release boundary, not as another
copy of the mutable legacy `Artists/` tree. The existing Fluency UI, playback,
song selection, progress identities, Card Data view and shell mechanics remain
the product baseline. The new architecture controls exactly which materialized
Artist outputs that UI can see.

The locally active audit release is:

- release: `lyrics-legacy-parity-20260822`
- location: `<workspace>/releases/lyrics/lyrics-legacy-parity-20260822/`
- sources: Bad Bunny, Rosalía, Young Miko, Joshua's Spanish test playlist and
  the French test playlist
- languages: Spanish and French
- total source-card rows: 21,678
- app files: 36 exact, hashed files (65,069,572 bytes)
- assignment status:
  `historical_materialized_assignments_preserved_for_product_parity`

This is sufficient to continue with the app and Artist pipeline audit. It does
not claim that the historical Artist assignments were produced by the clean
Speech WSD method.

## Folder and routing contract

The code repository owns contracts and app code only:

```text
src/fluency/artist/
  release.py                 build, validate, activate and resolve catalogs
src/fluency/lyrics/
  records.py                 stable song, line and optional alignment identities
  lineage.py                 append-only typed pipeline events
  ingest.py                  immutable source-ingestion stage and legacy adapter
schemas/
  lyrics-release-manifest.schema.json
  lyrics-release-composition.schema.json
  lyrics-lineage-event.schema.json      shared event vocabulary for every language
  lyrics-audit-bundle.schema.json       portable one-song audit payload
  raw-lyrics-song.schema.json
  lyrics-line.schema.json
  lyrics-line-alignment.schema.json
app/
  config/artists.json        empty static fallback only
  lyrics-audit/              development-only lineage explorer
```

Generated data remains outside git:

```text
<workspace>/releases/lyrics/
  active.json
  <release-id>/
    manifest.json
    composition.json
    app/
      config/artists.json
      Artists/
        spotify_tracks.json
        es/
          vocabulary_master.json
          <artist>/index.json
          <artist>/examples.json
          <artist>/songs.json          optional
          <artist>/albums.json         optional
          <artist>/Images/*            optional
        fr/
          vocabulary_master.json
          <artist>/index.json
          <artist>/examples.json
```

The app keeps its familiar stable URLs. The local server resolves
`/config/artists.json` and `/Artists/*` through `active.json`. The service
worker never caches those mutable aliases, so activating another exact release
cannot silently blend it with the old one. The catalog request also has a
one-time contract query key to escape the old application's cached empty
catalog during migration.

## What was retained

Only files referenced by the reviewed artist catalog were retained:

- split indexes and split example maps;
- language vocabulary masters required to reconstruct the app cards;
- song catalogs used by whole-artist and custom-playlist selection;
- album dictionaries, referenced artwork and the Spotify track map;
- historical assignment fields and their available prompt/run sidecars;
- the existing progress, selected-song and selected-artist identity contracts.

Each index must have unique card IDs and exactly the same ID set as its example
map. Every emitted app file is declared by path, byte size and SHA-256 content
identity. Catalog entries carry the active release ID and manifest/composition
paths, so audit flags can identify the release and Artist source layer.

## What was cut

The migration does not copy:

- the legacy mutable `Artists/` directory into the code repository;
- deleted or debugging monoliths;
- alternate `?variant=` monolith loading;
- unreferenced artwork and intermediate pipeline folders;
- preview files, notebooks or source-specific build dependencies;
- an implicit fallback to a prior Artist release;
- a claim that historical assignments are clean or current WSD results.

The old French config referred to a deleted monolith. The importer resolves its
existing split index/examples pair and does not recreate the monolith.

## Product-parity verification

The local app was verified through:

1. Spanish Speech to the Lyrics source picker.
2. Bad Bunny setup with 295 songs, artwork, percentage levels and stable sets.
3. A 20-card Learn set, card flip, lyric example and all example metadata in
   Card Data.
4. Choose-your-own mode across the available Spanish artists, selecting one
   song and rebuilding a 14-card deck.
5. French Artist setup with no song catalog or artwork; both optional fields
   degrade cleanly while its 1,455-card source remains usable.
6. Switching back to Speech without changing either Speech release.

## Lineage explorer checkpoint

The first end-to-end audit slice uses Bad Bunny's `Estamos Arriba` and compares
two preserved normalization runs. It contains the whole song (61 lines and 585
stable occurrences), highlights 84 direct changes, and connects the selected
token to the current routing and immutable app-release snapshots wherever a
safe identity join exists.

The explorer deliberately does not invent missing history. Direct claims,
reconstructed lookups, materialized snapshots and future human-review claims
are different evidence kinds in the contract. A token without a safe join says
so. This fixture is the reference UI for the new pipeline, not a replacement
for the learner-facing app.

The generic stage vocabulary is: acquire, extract, align, normalize, tag, route, menu,
assign, consolidate, assemble and review. Language-specific behavior belongs in
adapter metadata and decision payloads, so Spanish elision restoration does not
become a required French, Portuguese or Dutch pipeline stage.

The first clean source-ingestion runs are preserved under
`runs/es/lyrics/`. `bad-bunny-estamos-arriba-source-v1` proves that a missing
song in the historical aligned-translation file degrades to 61 valid source
lines and zero translations. It was not overwritten.
`bad-bunny-estamos-arriba-source-v2` uses the separately preserved flat
translation map and emits 61 lines, 43 optional alignments, 18 explicit
alignment absences and 105 lineage events. Both raw legacy inputs are pinned by
content identity in the workspace object store. No routing, WSD, deck or active
release changed.

## Remaining Artist work

These are subsequent R&D phases, not blockers for starting the Artist audit:

1. ~~Define a language-agnostic raw-lyrics and line-alignment source contract.~~
   Completed with a real immutable Bad Bunny source run.
2. Make every subsequent pipeline stage emit the lineage event contract while it runs,
   rather than reconstructing lineage after materialization.
3. Build a clean Artist inventory/example/assignment pipeline that emits the
   same split app contract.
4. Recompute assignments with the selected shared WSD architecture and explicit
   language adapters; do not modify this parity release in place.
5. Publish a new immutable release and compare it against this parity baseline.
6. Add new languages by catalog/config and typed source adapters, with song,
   artwork, translation, timestamps and playback all remaining optional.
7. Move offline Artist downloads to release-versioned URLs before claiming
   offline release switching. The stable active aliases intentionally fail
   closed when offline today.

The key separation is now enforceable: shell and study behavior can evolve
without rebuilding corpus data, while a new Artist data run can be activated
without changing the application or contaminating another run.
