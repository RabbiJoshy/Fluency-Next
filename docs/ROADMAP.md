# Fluency Next migration roadmap

## Purpose

This is the canonical long-running migration plan agreed with Josh. Read this
file first after a context reset, then read `BUILD_STATUS.md` and the numbered
decision records for the exact implementation state.

The goal is to make Fluency Next the eventual live application: the same
Fluency product experience, backed by a much smaller, auditable repository in
which languages, pipeline experiments, and exact combinations of runs can be
changed without stale data, accidental fallback, or hidden legacy machinery.

## Working agreement

- Work through one layer at a time and stop for Josh's approval at material
  decisions and at the end of each roadmap step.
- Explain which folders and contracts are being introduced for every layer.
- Give Josh exact local commands for expensive downloads, corpus scans,
  embeddings, WSD, and other long runs; inspect their outputs before advancing.
- Treat harvesting and WSD as independent stages.
- Use fresh, explicitly selected inputs. Do not import historical sentences,
  assignments, deck data, or dependencies merely because they already exist.
- Never combine, substitute, or fall back to another run implicitly. Every
  release declares exact artifact hashes, and activation remains manual.
- Speech card identity is the surface form. Lemmas may be lookup or linguistic
  metadata, but never the card/index identity.
- Preserve the existing Fluency app experience unless Josh explicitly approves
  a product change. Refactoring for clarity or performance is welcome only when
  behaviour remains equivalent or the change is separately identified.
- Keep the first compact pilot interface as a reference; it is not the live app
  baseline.

## Step 1 — Language-agnostic harvesting

**Status: complete in commit `7784d1a`; signed off 2026-08-22.**

Build one streaming harvesting engine with shared Speech rules, replaceable
language policies, and replaceable corpus adapters. Tatoeba and aligned
OpenSubtitles must emit one canonical parallel-sentence record while retaining
their different provenance. Source selection is explicit; nearby-word density
is not a selection signal; candidate pools remain larger than the final three
examples.

Implemented boundaries:

- `config/harvest/shared/` — cross-language Speech rules.
- `config/harvest/languages/` — language-specific normalization and quirks.
- `config/harvest/sources/` — source adapter contracts.
- `src/fluency/harvest/` — shared engine and Tatoeba/OpenSubtitles adapters.
- `<workspace>/runs/<language>/speech/<run-id>/stages/03_sentence_harvest/`
  — immutable, run-owned output.

No real French corpus run and no WSD were executed in this step.

## Step 2 — Port and generalize the best Spanish WSD

**Status: Spanish reference audit complete; architecture proposal awaiting
sign-off in `proposals/0001-wsd-port-architecture.md`.**

Audit the current best Spanish WSD implementation, separate its genuinely
language-agnostic retrieval/assignment machinery from Spanish-only behaviour,
and rebuild it behind stable contracts. French and future languages may use
different dictionary menus, morphology, lemmatization, clitic handling,
embedding models, rerankers, and calibration. Those differences must be
explicit language adapters rather than forks or hidden conditions.

The architecture must be built without waiting for final WSD quality choices.
Model revisions, calibration evidence, scores, rejection reasons, and assignment
status remain inspectable. Spanish BETO/calibration data must not be presented
as a valid French model merely to make the pipeline run.

## Step 3 — Audit the transplanted application frontend

**Status: exact app transplant exists; cleanup audit not started.**

Audit the transplanted HTML, CSS, and JavaScript for redundancy, stale paths,
obsolete compatibility behaviour, and performance problems. The baseline is
the actual Fluency application, not a redesigned replacement. Any proposed UX
change must be labelled as an improvement rather than described as migration.

Retain the approved numbered-card scrubber animation. Preserve the useful pilot
Card Data design as a reference, including example-first inspection of every
example's complete metadata and sense assignment.

## Step 4 — Truncated real French run and deck audit

**Status: not started.**

Create a fresh, small French run using real corpus data—likely OpenSubtitles
when its French snapshot is ready. Build and inspect the surface inventory,
sense menus, harvested candidates, WSD assignments, final three examples per
card, ordering, release artifacts, and exact app rendering. The intended audit
target is 200 surface cards × 3 final examples; a 20-card rehearsal may be used
first to prove commands and contracts cheaply.

Josh runs expensive commands locally; the assistant audits each resulting
folder and report. Shortfalls block release rather than borrowing old data.
The candidate is tested locally and stays inactive until explicitly approved.

## Step 5 — Migrate Spanish into the clean architecture

**Status: not started.**

Move the current Spanish Speech system into the same clean contracts after the
French vertical slice has proved them. Preserve the already completed Spanish
surface-form migration; do not reopen lemma indexing as an identity decision.
Rebuild or deliberately import only reviewed assets whose provenance and value
justify them. Spanish and French should share orchestration, artifact, release,
and debugging machinery while retaining explicit language adapters.

## Step 6 — Migrate Artist mode and shell mechanics

**Status: not started.**

Bring Artist mode, artist-specific data and selection, playback/shell mechanics,
and shared app integration into the clean release architecture. Artist mode is
eventually supported for every language and should reuse stable cards, senses,
progress identities, release selection, and common pipeline layers wherever
the semantics genuinely match.

Artist-specific evidence and presentation remain explicit layers rather than
being mixed invisibly into Speech runs.

## Completion condition

Fluency Next becomes the live repository only after the locally tested app has
behavioural parity, clean French and Spanish data paths, deliberate release
selection, migration-safe progress identities, and the required Artist/shell
features. The old live application is deprecated only after the replacement is
validated and deployed separately; local testing never requires changing the
existing GitHub application.
