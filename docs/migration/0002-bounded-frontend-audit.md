# Bounded frontend migration audit

## Purpose

This is a stopping-point audit, not a redesign. It records what was safe and
useful to change before migrating Spanish and Lyrics, and prevents later work
from reopening every old compatibility decision at once.

## Fixed now

- Removed the abandoned query-only Spanish Speech preview. Clean Spanish will
  enter through the same immutable release boundary as French.
- Removed the unused pipe-delimited CSV deck loader. Every configured language
  already uses JSON, and retaining a second unvalidated loader hid the real app
  data contract.
- Added browser-side guards for vocabulary indexes and split example files.
  Missing IDs, duplicate IDs, missing words/meanings, malformed example
  buckets, missing configured files, and invalid top-level shapes now stop with
  a source-specific error. Errors are also retained in
  `window._dataContractIssues` for inspection.
- Strengthened release validation so optional level/set rank metadata must
  agree with the exact ordered card IDs. A release can no longer declare one
  membership and make the app display another range silently.
- Made Card Data available to guest users. Private issue submission remains an
  owner-only control.

## Kept deliberately

- The existing Lyrics/Artist runtime, song selection, playback integrations,
  progress, authentication, sync, and offline machinery. These are large but
  are product features scheduled for migration, not proven dead code.
- Legacy CEFR/PPM behavior needed by data that has not yet moved to release-owned
  levels. It should disappear language by language, not in a speculative bulk
  deletion.
- Existing language-specific display fallbacks while only French is live in
  the new architecture. New generated data must use canonical `target` and
  `english` fields; remaining fallbacks can be removed when Spanish is migrated
  and tested against that contract.

## Deliberately deferred

- Define a separate `artist-deck/v1` contract. It should share stable identity,
  progress, release selection, provenance, and example primitives with Speech,
  while allowing Lyrics-specific evidence and an optional English translation.
  Speech translations remain required.
- Make app study-set selection consume exact `card_ids` directly rather than
  converting release sets back to rank ranges. Current clean Speech sets are
  contiguous and now validated; exact IDs become important once filtering and
  Artist-owned ordering enter the release system.
- Replace all target-language-name fallbacks with one canonical example
  accessor after Spanish proves the `target`/`english` boundary.
- Replace field-scanning feature detection with release-declared capabilities
  when Artist releases are introduced.
- Remove stale paths from disabled languages during each language migration,
  where their actual replacement can be verified.

## Exit criterion

The useful pre-Spanish cleanup is complete when tests pass and the transplanted
French app still loads, studies, and exposes Card Data. Further line-count or
style cleanup is intentionally postponed; the next architecture work is the
Spanish Speech migration, followed by the Lyrics/Artist contract.
