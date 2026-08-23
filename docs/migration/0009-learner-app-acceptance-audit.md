# Learner-app acceptance audit

**Date:** 2026-08-23  
**Scope:** bounded parity, persistence, offline and release-selection audit  
**Deployment:** inactive local candidate only

## Boundary

This audit does not decide whether every final production deck must be rebuilt
from clean runs or may retain reviewed legacy work. French is expected to move
to a full clean run. The retained Bad Bunny/Gemini work remains valuable until
Josh makes the separate data-retention decision. Production deployment and
deprecation of the old repository are therefore deferred.

## Learner flows exercised

- Bad Bunny, Rosalía, Young Miko and the French test playlist all loaded their
  release-owned levels and Learn actions.
- Whole-artist selection and the Spanish cross-artist custom source loaded.
- JSTA saved a three-song cross-artist playlist: `Estamos Arriba`, `DESPECHÁ`
  and `offline`. It survived reload, and the deployed SongSets endpoint returned
  the exact three song IDs plus `bad-bunny`, `rosalia` and `young-miko` source
  provenance. A completely fresh local origin then logged in as JSTA and
  restored the same `3 of 506 songs` selection from the backend.
- A Bad Bunny Learn set resumed at the exact unfinished card, completed, and
  produced a non-empty Review queue. Progress remained visible after reload.
- Card Data exposed example-first retained assignment, translation, song,
  method, release and run evidence.
- JSTA submitted one deliberate note flag from the real card interface. The UI
  attached release `lyrics-legacy-parity-20260822` and run
  `run_9b10a162edde17313dc83ff5` before submission. After the durable queue
  drained, the deployed FlaggedWords sheet contained flag
  `ddf999e7-0be9-42b5-85d6-993c249eff90` with those exact identifiers and a
  non-empty provenance JSON payload.

The audit intentionally changed JSTA test state: Bad Bunny Level 1 Set 1 is
complete, four cards in Set 2 were graded during the completion-path exercise,
and one unfinished Review card remains. This is audit-account data, not a
production learner account.

## Problems found and fixed

1. French Artist mode worked by direct URL but the new language-first chooser
   declared French Lyrics unavailable. French now declares the capability and
   its picker exposes `TestPlaylist (French)` without first loading Speech.
2. An explicit Lyrics offline download retained the complete immutable release,
   but offline boot still depended on the network-only active catalogue alias.
   The alias remains network-authoritative online. On network failure it may
   now fall back only to the exact catalogue installed through the current
   offline manifest; it cannot select an arbitrary cached historical release.
3. Two remaining help strings described the retired language-immediately-loads-
   Speech flow. They now describe language followed by Speech/Lyrics selection.
4. A playlist saved before login did not reconcile when the user subsequently
   entered initials, and the 3.5-second request timeout was shorter than the
   observed Apps Script response. Named login now explicitly reconciles the
   already-loaded song catalogue through a retry-safe 12-second boundary.

No additional app branch was removed merely for reducing line count. The
bounded scan found no further code that was both clearly unreachable and safe
to delete independently of the pending clean-versus-retained deck decision.

## Deployment candidate

`fluency-next-acceptance-candidate-20260823-v4` contains 91 hashed files and
75,660,754 bytes. It selects exactly:

- Spanish Speech `es-speech-audit-200-unassigned-jehle-20260822`;
- French Speech `fr-speech-real-tatoeba-unassigned-0003`;
- Lyrics `lyrics-legacy-parity-20260822`.

Backend secrets, development documentation and the lineage explorer are not in
the static site. Nothing was uploaded, activated or deprecated.

## Offline and release tests

- The v2 candidate served through an ordinary static HTTP server; the final v4
  includes the same verified offline behavior plus corrected help and fresh-
  login synchronization, and was integrity-validated by the same builder.
- Its explicit Lyrics download installed 62.1 MB and all five Artist sources.
- With the server then stopped, a fresh guest launch of the Bad Bunny route
  still rendered all 295 songs, levels and the Learn action.
- Explicit preview selection loaded the one-song/17-card
  `lyrics-clean-estamos-arriba-preview-20260823` release.
- Removing the preview selector returned to the active 295-song retained parity
  release; no release alias was activated or rewritten.

## Remaining gate before optional deployment

- Record the final clean-versus-retained data decision and rebuild the same
  static candidate against the chosen release IDs if they change.
- Production deployment remains a separate, explicit approval step with the old
  app retained as rollback.
