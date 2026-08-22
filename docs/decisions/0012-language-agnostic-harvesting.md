# Decision 0012: language-agnostic sentence harvesting

## Status

Accepted and implemented on 2026-08-22. This decision covers harvesting only;
it does not select or execute a WSD method.

## Decision

Sentence harvesting is one shared engine with three replaceable policy layers:

1. a shared Speech quality and easiness policy;
2. a language policy for normalization, token boundaries, and exceptional
   sentence rules;
3. one or more explicitly selected source adapters.

French currently keeps apostrophes and hyphens. A future language may reject or
tokenize them differently by changing its language policy without forking the
harvester. Cards and candidate indexes are keyed only by stable surface-card
identity; lemma fields are rejected from the harvest inventory.

Every source adapter emits the same `parallel-sentence/v1` record. Shared fields
cover target text, translation, adapter, snapshot hash, source record ID,
license, and attribution. Source-specific evidence remains optional inside the
source record: Tatoeba carries both sentence IDs and contributors;
OpenSubtitles carries title, subtitle, and line provenance.

## Source selection and run isolation

A profile must choose `exclusive` or `explicit_union` and name every source.
The command must supply exactly those sources. It cannot silently add Tatoeba,
substitute OpenSubtitles, search an old repository, or reuse another run's
candidate bank.

Raw snapshots must live under the external workspace's append-only `raw/`
directory. The harvester reads the surface inventory and frequency ranks only
from `stages/01_inventory/output/` in the same run. Output is promoted once to
`stages/03_sentence_harvest/output/`; a second execution refuses to overwrite
it and requires a new run ID.

The stage retains up to 60 easiest candidates per surface. It does not choose
the learner's final three examples. Candidate scores are based on sentence
length and frequency burden; nearby target-word density is not used. Shortfalls
are reported and block a later release, but they do not borrow old examples.

## Supported adapters

- `tatoeba/v1` streams the bilingual ZIP and preserves its CC-BY attribution,
  sentence IDs, contributors, URLs, archive date when present, and snapshot
  hash.
- `opensubtitles-aligned/v1` streams three aligned target, English, and `.ids`
  files. A required `snapshot.json` supplies the exact corpus snapshot ID,
  license, attribution, and source URL. Alignment-length mismatches fail closed.

Adding another source requires one policy file and one adapter implementing the
small corpus-adapter protocol; the matching, quality, scoring, candidate,
manifest, and reporting layers remain unchanged.
