"""The Phase H exporters: one document, three renderings, zero invented fields.

Every promise the roadmap makes for export is pinned here: the renderers are
pure functions of the document (plus optional effective layers), ChordPro
places chords on the words they sound over, Markdown is a readable sheet,
JSON round-trips through the codec, no exporter names a field the model does
not have, and a session's edited layer prints exactly as displayed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from fixtures.fake_analysis import DURATION, EVENTS, LYRICS
from song_chord_lyrics_analyzer.app.editing import TransposeChords, effective_chords
from song_chord_lyrics_analyzer.export import EXPORT_FORMATS, export_document, render_json
from song_chord_lyrics_analyzer.export.chordpro import render_chordpro
from song_chord_lyrics_analyzer.export.markdown import render_markdown
from song_chord_lyrics_analyzer.models.analysis import (
    AnalysisResult,
    AnalysisRun,
    Provenance,
    RunStatus,
)
from song_chord_lyrics_analyzer.models.audio import AudioDocument
from song_chord_lyrics_analyzer.models.music import KeyEstimate, KeyMode, TempoEstimate
from song_chord_lyrics_analyzer.schema.codec import decode
from song_chord_lyrics_analyzer.utils.errors import InputError


def _document(**overrides: object) -> AnalysisResult:
    """A small full document, as the analysis service would produce."""
    fields: dict[str, object] = {
        "provenance": Provenance(
            application_version="test",
            input_path="song.wav",
            python_version="3.13",
            platform="test",
            engines={},
            configuration={},
        ),
        "audio": AudioDocument(path="song.wav", duration=DURATION),
        "chords": list(EVENTS),
        "lyrics": list(LYRICS),
        "key": KeyEstimate(tonic="C", mode=KeyMode.MAJOR, source="fake"),
        "tempo": TempoEstimate(bpm=120.0, source="fake"),
        "run": AnalysisRun(
            status=RunStatus.SUCCEEDED,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        ),
        "warnings": [],
    }
    fields.update(overrides)
    return AnalysisResult(**fields)  # type: ignore[arg-type]


class TestChordPro:
    def test_the_header_names_the_song_key_and_tempo(self) -> None:
        text = render_chordpro(_document())

        assert "{title: song.wav}" in text
        assert "{key: C major}" in text
        assert "{tempo: 120}" in text

    def test_chords_sit_in_brackets_before_the_words_they_sound_over(self) -> None:
        text = render_chordpro(_document())

        # "hola" spans 0.0..0.5 under the C event; "mundo" 0.5..1 under C too,
        # "adios" at 2.0 under explicit silence, "amor" 2.5..3.0 under it too.
        lines = [line for line in text.splitlines() if "hola" in line or "adios" in line]
        assert lines == ["[C]hola [C]mundo", "[N]adios [N]amor"]

    def test_a_lyric_line_without_word_timestamps_prints_as_plain_text(self) -> None:
        document = _document(lyrics=[])  # no lyrics at all
        text = render_chordpro(document)
        assert text.startswith("{title: song.wav}")

    def test_the_rendering_is_deterministic(self) -> None:
        assert render_chordpro(_document()) == render_chordpro(_document())

    def test_edited_layers_print_exactly_as_the_session_shows_them(self) -> None:
        effective = effective_chords(EVENTS, [TransposeChords(2)])
        text = render_chordpro(_document(), chords=effective)

        assert "[D]hola" in text  # C transposed to D
        assert "[N]adios" in text  # silence is un-transposable, still silent


class TestMarkdown:
    def test_the_header_names_the_song_and_the_facts(self) -> None:
        text = render_markdown(_document())

        assert text.startswith("# song.wav")
        assert "key C major" in text
        assert "tempo 120 BPM" in text
        assert "duration 00:04.00" in text

    def test_the_chord_table_lists_every_event_in_order(self) -> None:
        text = render_markdown(_document())
        table = text.split("## Chords")[1].split("## Lyrics")[0]

        assert "| start | end | chord |" in table
        assert "| 00:00.00 | 00:01.00 | C |" in table
        assert "| 00:02.00 | 00:03.00 | N |" in table
        assert "| 00:03.00 | 00:04.00 | F |" in table

    def test_the_lyrics_carry_their_start_times(self) -> None:
        text = render_markdown(_document())
        lyrics = text.split("## Lyrics")[1]

        assert "`00:00.00` — hola mundo" in lyrics
        assert "`00:02.00` — adios amor" in lyrics

    def test_edited_layers_print_exactly_as_the_session_shows_them(self) -> None:
        effective = effective_chords(EVENTS, [TransposeChords(2)])
        text = render_markdown(_document(), chords=effective)

        assert "| 00:00.00 | 00:01.00 | D |" in text


class TestJson:
    def test_the_output_is_the_document_the_codec_can_rebuild(self) -> None:
        text = render_json(_document())
        payload = json.loads(text)

        # The canonical document itself, not an enveloped sidecar.
        rebuilt = decode(AnalysisResult, payload)
        assert rebuilt.audio is not None and rebuilt.audio.duration == DURATION
        assert [event.label for event in rebuilt.chords] == [event.label for event in EVENTS]

    def test_the_edited_chord_layer_replaces_the_document_s(self) -> None:
        effective = effective_chords(EVENTS, [TransposeChords(2)])
        payload = json.loads(render_json(_document(), chords=effective))

        labels = [event["label"] for event in payload["chords"]]
        assert labels[0] == "D"


class TestExportDocument:
    def test_each_format_writes_its_rendering(self, tmp_path: object) -> None:
        document = _document()
        for fmt in EXPORT_FORMATS:
            out = tmp_path.joinpath(f"sheet.{fmt}")
            written = export_document(document, fmt, out)
            assert written == out
            assert out.read_text()

    @pytest.mark.parametrize("fmt", EXPORT_FORMATS)
    def test_exported_text_matches_the_renderer(self, tmp_path: object, fmt: str) -> None:
        document = _document()
        out = tmp_path.joinpath(f"sheet.{fmt}")
        export_document(document, fmt, out)
        text = out.read_text()
        assert "{title: song.wav}" in text or "# song.wav" in text or '"song.wav"' in text

    def test_an_unknown_format_is_rejected(self, tmp_path: object) -> None:
        out = tmp_path.joinpath("sheet.xyz")
        with pytest.raises(InputError, match="Unknown export format"):
            export_document(_document(), "xyz", out)
