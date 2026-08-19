# 0002: Local development bootstrap

- Status: Accepted
- Date: 2026-08-20

## Decision

Use Python 3.12 and a standard local virtual environment. Do not introduce Node
or a JavaScript build tool during bootstrap. Serve the static app through the
Python CLI at `http://127.0.0.1:4173`.

Initialize local Git history without a remote. GitHub creation and deployment are
later publication decisions, not prerequisites for development.

## Consequences

- The bootstrap has no runtime dependencies outside the Python standard library.
- Browser behavior is tested through HTTP rather than by opening files directly.
- Production storage, service workers, APIs, and releases remain disconnected.
- A JavaScript build system can be proposed later only if concrete app needs
  justify its cost.

