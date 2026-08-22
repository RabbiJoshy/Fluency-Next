# Decision 0009: study lifecycle migration

## Status

Accepted and implemented in Gate 9.

## Context

The compact runtime had restored the original product shell and active card
experience, but its setup treated the pilot as one hard-coded queue. The
original app distinguishes learning unseen cards from reviewing unfinished
cards, resumes an interrupted set, and has an established completion flow.
Those behaviours must survive the migration without allowing a newly activated
research run to alter an existing session.

## Migrated existing behaviour

- A release declares stable levels, sets, and ordered card membership.
- Learn contains only unseen cards from the selected set.
- Review is separate and contains review cards across the selected level.
- A fully seen set can be studied again.
- Leaving a session and returning shows the existing welcome-back choice to
  continue the set or choose a new one.
- Completion reports correct, missed, and accuracy totals. Learn may continue
  automatically to the next unseen set; Main menu and Redo set remain
  available.

These are migrations of existing product behaviour, not proposed product
changes. In particular, Gate 9 does not add a Review mistakes completion action.

## Internal safety architecture

New releases must include `study-structure/v1`, and validation requires every
deck card to appear exactly once. A session snapshot freezes the exact release
ID, level, set, queue type, ordered card IDs, position, card side, example,
direction, speech preference, and session results.

Resume never rebuilds the queue from the current active release. If the saved
release differs, the app offers to open that exact catalogued release. If it is
unavailable, resume remains disabled rather than remapping card IDs.

Releases `fr-speech-pilot-0002` and `0003` predate the new contract. Catalog and
runtime code may expose them through a clearly labelled, single-set
compatibility adapter after their original hashes are verified. Their release
files remain immutable, and their data is never blended with another release.

## Deferred decisions

Multi-set production French membership, due-date scheduling, Spanish progress
migration, and any completion-flow improvements remain separate decisions.
