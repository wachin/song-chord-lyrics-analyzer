"""Unit tests for chord normalization and transposition (roadmap section 65)."""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.models import ChordQuality
from song_chord_lyrics_analyzer.normalization import (
    normalize_note_name,
    parse_chord_label,
    render_chord_label,
    transpose_chord_label,
    transpose_note_name,
)


class TestParseChordLabel:
    @pytest.mark.parametrize(
        ("label", "root", "quality", "bass"),
        [
            ("C", "C", ChordQuality.MAJOR, None),
            ("G", "G", ChordQuality.MAJOR, None),
            ("Am", "A", ChordQuality.MINOR, None),
            ("F", "F", ChordQuality.MAJOR, None),
            ("C#m", "C#", ChordQuality.MINOR, None),
            ("Bbmaj7", "A#", ChordQuality.MAJOR7, None),
            ("Dm7", "D", ChordQuality.MINOR7, None),
            ("G7", "G", ChordQuality.DOMINANT7, None),
            ("Dsus4", "D", ChordQuality.SUS4, None),
            ("Bdim", "B", ChordQuality.DIMINISHED, None),
            ("Caug", "C", ChordQuality.AUGMENTED, None),
            ("Cadd9", "C", ChordQuality.ADD9, None),
            ("C6", "C", ChordQuality.SIXTH, None),
            ("Am6", "A", ChordQuality.MINOR_SIXTH, None),
            ("C9", "C", ChordQuality.NINTH, None),
            ("Am9", "A", ChordQuality.MINOR_NINTH, None),
            ("C/E", "C", ChordQuality.MAJOR, "E"),
            ("Am/G", "A", ChordQuality.MINOR, "G"),
        ],
    )
    def test_recognized_labels(
        self, label: str, root: str, quality: ChordQuality, bass: str | None
    ) -> None:
        parsed = parse_chord_label(label)
        assert parsed.root == root
        assert parsed.quality is quality
        assert parsed.bass == bass
        assert parsed.is_recognized is True
        assert parsed.raw == label

    @pytest.mark.parametrize("label", ["N", "n", "NC", "no chord", "none"])
    def test_no_chord_labels(self, label: str) -> None:
        parsed = parse_chord_label(label)
        assert parsed.is_no_chord is True
        assert parsed.label == "N"

    def test_unicode_symbols_are_understood(self) -> None:
        assert parse_chord_label("C\u266f").root == "C#"
        assert parse_chord_label("B\u266d").root == "A#"
        assert parse_chord_label("C\u03947").quality is ChordQuality.MAJOR7
        assert parse_chord_label("C\u00b0").quality is ChordQuality.DIMINISHED

    def test_major_seventh_is_not_confused_with_minor_seventh(self) -> None:
        assert parse_chord_label("CM7").quality is ChordQuality.MAJOR7
        assert parse_chord_label("Cm7").quality is ChordQuality.MINOR7
        assert parse_chord_label("CM7").label == "Cmaj7"

    def test_unknown_suffix_is_preserved_not_invented(self) -> None:
        parsed = parse_chord_label("C7#11")
        assert parsed.quality is ChordQuality.OTHER
        assert parsed.is_recognized is False
        assert parsed.extensions == ("7#11",)
        assert parsed.label == "C7#11"
        assert parsed.raw == "C7#11"

    def test_unparsable_label_keeps_raw_text(self) -> None:
        parsed = parse_chord_label("???")
        assert parsed.quality is ChordQuality.UNKNOWN
        assert parsed.root is None
        assert parsed.raw == "???"

    def test_empty_label_is_unknown_not_silence(self) -> None:
        parsed = parse_chord_label("   ")
        assert parsed.quality is ChordQuality.UNKNOWN
        assert parsed.is_no_chord is False

    def test_invalid_slash_bass_is_kept_verbatim(self) -> None:
        parsed = parse_chord_label("C/something")
        assert parsed.quality is ChordQuality.OTHER
        assert parsed.extensions == ("/something",)

    def test_whitespace_is_trimmed(self) -> None:
        assert parse_chord_label("  Am  ").label == "Am"


class TestRenderChordLabel:
    def test_render_uses_canonical_suffixes(self) -> None:
        assert render_chord_label("C", ChordQuality.MINOR) == "Cm"
        assert render_chord_label("C", ChordQuality.MAJOR7) == "Cmaj7"
        assert render_chord_label("A", ChordQuality.MINOR, bass="G") == "Am/G"

    def test_render_no_chord(self) -> None:
        assert render_chord_label(None, ChordQuality.NO_CHORD) == "N"

    def test_render_unknown_is_not_silence(self) -> None:
        assert render_chord_label(None, ChordQuality.UNKNOWN) == "?"


class TestNoteNames:
    def test_normalize_flats_to_sharps(self) -> None:
        assert normalize_note_name("Bb") == "A#"
        assert normalize_note_name("eb") == "D#"
        assert normalize_note_name("C") == "C"

    def test_normalize_rejects_unknown_notes(self) -> None:
        with pytest.raises(ValueError):
            normalize_note_name("H")
        with pytest.raises(ValueError):
            normalize_note_name("")

    def test_transpose_note_wraps_around(self) -> None:
        assert transpose_note_name("C", 2) == "D"
        assert transpose_note_name("B", 1) == "C"
        assert transpose_note_name("C", -1) == "B"
        assert transpose_note_name("C", 12) == "C"


class TestTransposeChordLabel:
    @pytest.mark.parametrize(
        ("label", "semitones", "expected"),
        [
            ("C", 2, "D"),
            ("Am", 2, "Bm"),
            ("F", 2, "G"),
            ("G", 2, "A"),
            ("Cmaj7", 2, "Dmaj7"),
            ("C/E", 2, "D/F#"),
            ("Bbmaj7", 1, "Bmaj7"),
            ("C", -1, "B"),
            ("C", -2, "A#"),
        ],
    )
    def test_transposition(self, label: str, semitones: int, expected: str) -> None:
        assert transpose_chord_label(label, semitones) == expected

    def test_no_chord_is_preserved(self) -> None:
        assert transpose_chord_label("N", 3) == "N"

    def test_unrecognized_label_is_left_untouched(self) -> None:
        assert transpose_chord_label("C7#11", 2) == "C7#11"
        assert transpose_chord_label("???", 2) == "???"
