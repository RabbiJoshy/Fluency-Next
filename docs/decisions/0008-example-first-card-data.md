# Decision 0008 — Example-first Card Data inspection

## Status

Accepted and implemented on 2026-08-22.

## Decision

The active-study information surface is organized by example, because an
example-to-sense assignment is the unit being inspected during WSD research.
The top-level scrubber traverses every example attached to the active surface
card. Each position shows:

- target and English sentence text;
- every field recorded on the example object;
- the resolved assigned sense and every field recorded on that sense;
- explicit assignment method, confidence and run ID rows, including `not
  recorded` when the release contains no such claim;
- sentence, WSD and example-selection layer provenance;
- fallback and manual-override state;
- release, deck and composition identities.

A collapsed full sense menu remains below the example evidence so the assigned
sense can be compared with every alternative without making senses the primary
navigation level.

The metadata renderer recursively enumerates future object and array fields.
Adding embedding, WSD score, candidate-ranking or model-provenance fields to a
future release therefore makes them inspectable without a one-off UI change.
Missing WSD is displayed as an omitted layer with its declared reason; the app
does not search another run for metadata.

The active-study gear opens the restored compact study menu: Main menu, card
direction, automatic speech, set progress, Card Data, and the release/layer
audit. These controls use the original Fluency HTML/CSS shell.

## Verification fixture

Immutable release `fr-speech-pilot-0003` adds two curated `bonjour` examples so
the example scrubber is exercised with three real positions. Release `0002`
remains unchanged and selectable for comparison.
