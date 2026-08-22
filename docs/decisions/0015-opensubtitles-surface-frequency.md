# Decision 0015 — OpenSubtitles surface frequency for Spanish Speech

## Decision

Rank Spanish Speech cards by observed surface-token frequency in the pinned
Spanish side of the aligned OpenSubtitles corpus. Do not use
`SpanishRawWiki.csv` as the new ranking authority.

The old CSV has 11,136 lemma-expanded rows but only 9,999 normalized surfaces.
Its converter divided one surface's occurrence count across every proposed
lemma, and its missing source text, URI and license prevent an honest claim
that the filename describes its upstream corpus. It remains comparison evidence
only.

The approved OpenSubtitles Spanish file is approximately 2 GB and contains
61,434,251 lines. Its exact bytes are pinned in the external workspace before
compilation. Upstream URI and license are recorded as unknown until recovered;
they are not invented.

## Architecture

`fluency frequency compile-corpus` performs the expensive scan once and writes:

```text
Fluency-Workspace/raw/frequency/es/opensubtitles/<snapshot-id>/
  manifest.json
  surface-frequencies.tsv
```

The manifest binds the raw corpus hash, byte/line/token counts, normalization
configuration, compiler implementation, output hash and provenance. Snapshot
directories are immutable and refuse overwrite.

The ordinary `fluency pipeline inventory` stage consumes this ranked snapshot
and selects a run's exact 20, 200 or later full card count. This separation
avoids repeating the 61-million-line scan without treating another run's
inventory as a fallback.

## Surface rules

- NFC normalize and casefold without accent folding.
- Count complete observed word surfaces; never split counts by lemma.
- Preserve attached clitic surfaces such as `dámelo` as card candidates.
- Use deterministic frequency-descending, surface-ascending tie order.
- Reject lines containing configured URL, markup or music markers and report
  the rejection count.

## Verification

Fixture tests prove raw/input and compiled/output hashes, accented and clitic
surfaces, line rejection, overwrite refusal, workspace containment, quick
run-owned inventory selection and absence of release activation. The full
repository suite passes with 142 tests. The real corpus scan remains a local
long-running command.
