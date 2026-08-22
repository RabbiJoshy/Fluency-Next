# Spanish OpenSubtitles surface-frequency run

> Optional future re-ranking experiment. This is no longer required for the
> current Spanish migration; see Decision 0016.

## One-time raw snapshot pin

The source must live under the external workspace so Fluency Next remains
independent of the old repository. On APFS, `cp -c -p` creates a copy-on-write
clone and preserves timestamps without initially duplicating 2 GB of blocks.

```bash
mkdir -p /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/raw/corpora/es/opensubtitles/opensubtitles-en-es-2017-recovered-v1

cp -c -p /Users/joshuathomasamar/PycharmProjects/Fluency/Data/Spanish/corpora/opensubtitles/OpenSubtitles.en-es.es \
  /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/raw/corpora/es/opensubtitles/opensubtitles-en-es-2017-recovered-v1/OpenSubtitles.en-es.es
```

## Long compilation

Run from the Fluency Next repository. Progress is printed every million lines.
The command hashes and counts in the same pass and refuses to overwrite an
existing snapshot.

```bash
cd /Users/joshuathomasamar/PycharmProjects/Fluency-Next

PYTHONPATH=src python3.12 -m fluency frequency compile-corpus \
  --workspace /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace \
  --language es \
  --corpus /Users/joshuathomasamar/PycharmProjects/Fluency-Workspace/raw/corpora/es/opensubtitles/opensubtitles-en-es-2017-recovered-v1/OpenSubtitles.en-es.es \
  --snapshot-id opensubtitles-en-es-2017-recovered-v1 \
  --provider opensubtitles
```

Return the final three output lines. The assistant will verify the manifest and
rank table, then create and execute the quick 20-card inventory locally before
the 200-card decision gate.
