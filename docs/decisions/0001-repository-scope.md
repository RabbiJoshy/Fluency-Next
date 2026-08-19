# 0001: Repository scope

- Status: Accepted
- Date: 2026-08-20

## Decision

Use `Fluency-Next` as one future codebase for multiple languages and modes, with
French Speech as its first implementation. Keep large and generated artifacts in
the separate `Fluency-Workspace` root.

Language adapters define how text is understood. Mode adapters define where
content came from and how it is ranked and presented. Cards and learner progress
will belong to neither a source nor a mode.

## Consequences

- French can be built without copying a complete pipeline for later languages.
- Speech and Artist mode can share card and sense identities.
- Large corpora, models, embeddings, and runs do not enter the code repository.
- The existing Fluency repository remains the migration source until cutover.

