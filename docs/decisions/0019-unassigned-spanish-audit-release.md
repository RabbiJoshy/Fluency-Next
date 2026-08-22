# Decision 0019 — Unassigned Spanish audit release

## Decision

Publish a real 200-card Spanish audit release before WSD is attached. Select
three examples per surface from the run-owned retained candidate layer and mark
every example and dictionary meaning explicitly unassigned. SpanishDict options
remain browsable but no example is presented as evidence for a sense.

The release builder is language/provider-neutral: it derives the menu provider,
locale, label and progress namespace from the run rather than assuming French
or Wiktionary. Complete analysis and sense provider metadata is preserved into
the app compatibility index for Card Data auditing.

## Optional translations

An empty sense translation is accepted only when provider metadata says
`translation_status: explicit_missing` and a non-empty context remains. Other
blank meanings fail validation. This preserves SpanishDict construction-only
leaves without turning accidental missing data into a silent blank card.

## Verified release

Inactive release `es-speech-audit-200-unassigned-20260822` contains:

- 200 sequential surface cards;
- 2,352 SpanishDict meanings with complete provider metadata;
- exactly 600 examples, three for every card;
- no WSD assignments or sense claims;
- no source fallback;
- progress namespace `es-speech-next`.

The release validator accepts all four required layers: inventory, sense menu,
sentences and example selection. It was subsequently activated only in the
local workspace. The restarted development server serves all 200 cards and 600
examples through the ordinary Spanish aliases; no deployment occurred.
