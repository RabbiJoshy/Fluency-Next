from fluency.lyrics.ingest import _extract_lines, _legacy_translations
from fluency.lyrics.lineage import build_lineage_event, validate_lineage_event
from fluency.lyrics.records import build_song_id, validate_line_alignment, validate_lyrics_line


SNAPSHOT_ID = "sha256:" + "a" * 64


def test_source_line_identity_does_not_depend_on_translation() -> None:
    song_id = build_song_id(
        adapter="fixture/v1",
        snapshot_content_id=SNAPSHOT_ID,
        source_record_id="42",
    )
    lines = _extract_lines(
        song_id=song_id,
        language="pt",
        raw_text="Provider noise[Verso: Artista]\nUma linha\nOutra linha\n",
    )
    assert [line["text"] for line in lines] == ["Uma linha", "Outra linha"]
    assert lines[0]["section"]["performers"] == ["Artista"]
    for line in lines:
        validate_lyrics_line(line, song_id=song_id, language="pt")


def test_flat_legacy_translation_map_degrades_by_line() -> None:
    song_id = build_song_id(
        adapter="fixture/v1",
        snapshot_content_id=SNAPSHOT_ID,
        source_record_id="42",
    )
    lines = _extract_lines(
        song_id=song_id,
        language="nl",
        raw_text="[Couplet]\nEen regel\nNiet vertaald\n",
    )
    alignments = _legacy_translations(
        translations={"Een regel": {"english": "One line", "source": "human"}},
        source_record_id="42",
        lines=lines,
        target_language="en",
        snapshot_content_id=SNAPSHOT_ID,
    )
    assert len(alignments) == 1
    assert alignments[0]["source"]["provider"] == "human"
    validate_line_alignment(alignments[0], line_ids={line["line_id"] for line in lines})


def test_lineage_event_identity_is_deterministic() -> None:
    arguments = {
        "subject": {"kind": "segment", "id": "line_123"},
        "phase": "align",
        "operation": "align",
        "run_id": "run-1",
        "method_id": "fixture/v1",
        "input_refs": [{"kind": "lyrics_line", "id": "line_123"}],
        "output_refs": [{"kind": "line_alignment", "id": "alignment_123"}],
        "evidence_kind": "direct",
    }
    first = build_lineage_event(**arguments)
    second = build_lineage_event(**arguments)
    assert first == second
    validate_lineage_event(first)
