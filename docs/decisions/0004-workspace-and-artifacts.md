# 0004: External workspace and immutable artifacts

- Status: Accepted
- Date: 2026-08-20

## Decision

Keep raw inputs and generated data in `Fluency-Workspace`, outside the code
repository. Store large stage outputs once in a SHA-256 content-addressed object
store. Runs contain readable manifests, logs, statistics, rejections, and object
references rather than copied outputs.

Raw snapshots are append-only. Content-addressed objects, promoted registries,
and releases are immutable. Cache contents are disposable. Removal is recoverable
through quarantine before an explicit purge.

Each execution receives a timestamped run ID. Stage reuse is controlled by a
separate deterministic cache key containing the stage contract, implementation,
configuration, inputs, model revisions, and random seed.

Temporary outputs are written on the same filesystem as permanent objects and
atomically promoted only after validation and hashing.

## Consequences

- Repeated runs do not duplicate identical large outputs.
- Interrupted writes cannot masquerade as completed artifacts.
- Runs remain inspectable without opening large data files.
- Cache invalidation is local to the affected stage inputs and implementation.
- Raw data and referenced artifacts cannot be garbage-collected automatically.
- Code and generated data remain independently movable and publishable.

