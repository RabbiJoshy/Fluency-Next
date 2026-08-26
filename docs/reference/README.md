# Reference

Measurements and leads carried across from the Fluency repository, kept because
they record findings about the WSD *problem* rather than about the old
pipeline's machinery.

| File | What it is |
|---|---|
| `wsd_dead_ends.md` | Experiments implemented, measured and rejected. Re-running one costs a day and returns the same answer. |
| `portuguese-v7-baseline.md` | The first Portuguese WSD measurement, and the POS-bridge and ladder numbers behind it. Untuned by construction. |
| `wsd_open_threads.md` | Leads that were partly measured and not ruled out. Not a backlog; several are mutually exclusive and at least one is probably wrong. |

Both carry a header stating what they were measured on. That matters more than
usual here: findings about embedding behaviour transfer, findings about menu
structure are SpanishDict-specific, and findings about v5/v6 components may not
describe v7.

Deliberately **not** migrated, because they describe machinery this repository
does not have: `wsd_algorithm.md` (documents v5), `open_defects.md` (verifies
against `layers/*.json` paths), `method_priority.md`, `builder_flags.md`,
`sense_assignment_internals.md`, `pipeline_behaviors.md`,
`evidence_artifact_storage.md`, and `surface_identity_migration.md` (superseded
by `INVARIANTS.md`).
