"""Key-aware chord spelling for display (roadmap Phase F).

The canonical document stores sharp-spelled pitch classes; these tests pin the
presentation rule that respells them for a flat key without touching the model.
The two directions matter: a flat key must produce flats (``A#`` -> ``Bb``) and
an unknown key must keep the canonical spelling rather than guessing.
"""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.normalization.spelling import (
    prefers_flats,
    spell_chord_label,
    spell_key_label,
    spell_note_name,
)


class TestPrefersFlats:
    @pytest.mark.parametrize(
        ("tonic", "mode"),
        [
            ("F", "major"),
            ("A#", "major"),  # Bb major, the canonical model spells it A#
            ("D#", "major"),  # Eb major
            ("C#", "major"),  # Db major
            ("D", "minor"),  # D minor has one flat
            ("A#", "minor"),  # Bb minor has five flats
            ("C", "minor"),  # C minor has three flats
        ],
    )
    def test_flat_keys_are_recognised(self, tonic: str, mode: str) -> None:
        assert prefers_flats(tonic, mode) is True

    @pytest.mark.parametrize(
        ("tonic", "mode"),
        [
            ("C", "major"),
            ("G", "major"),
            ("B", "major"),
            ("F#", "major"),
            ("A", "minor"),
            ("E", "minor"),
            ("F#", "minor"),
        ],
    )
    def test_sharp_keys_are_not(self, tonic: str, mode: str) -> None:
        assert prefers_flats(tonic, mode) is False

    def test_an_unknown_key_keeps_the_canonical_spelling(self) -> None:
        assert prefers_flats(None, "major") is False
        assert prefers_flats("C", None) is False
        assert prefers_flats("C", "unknown") is False
        assert prefers_flats("H", "major") is False

    def test_the_mode_is_case_insensitive(self) -> None:
        assert prefers_flats("A#", "MAJOR") is True
        assert prefers_flats("D", "Minor") is True


class TestSpellNoteName:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [("A#", "Bb"), ("C#", "Db"), ("D#", "Eb"), ("F#", "Gb"), ("G#", "Ab")],
    )
    def test_sharp_names_gain_their_flat_spelling(self, name: str, expected: str) -> None:
        assert spell_note_name(name, prefer_flats=True) == expected

    @pytest.mark.parametrize("name", ["C", "D", "E", "F", "G", "A", "B"])
    def test_naturals_are_unchanged(self, name: str) -> None:
        assert spell_note_name(name, prefer_flats=True) == name

    def test_flat_input_stays_flat(self) -> None:
        assert spell_note_name("Bb", prefer_flats=True) == "Bb"

    def test_without_the_preference_the_canonical_name_is_returned(self) -> None:
        assert spell_note_name("A#", prefer_flats=False) == "A#"

    def test_unrecognised_text_passes_through(self) -> None:
        assert spell_note_name("H", prefer_flats=True) == "H"


class TestSpellChordLabel:
    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("A#", "Bb"),
            ("A#m", "Bbm"),
            ("A#m7", "Bbm7"),
            ("C#sus4", "Dbsus4"),
            ("F#/A#", "Gb/Bb"),
            ("A#m7/D#", "Bbm7/Eb"),
        ],
    )
    def test_roots_and_basses_are_respelled(self, label: str, expected: str) -> None:
        assert spell_chord_label(label, prefer_flats=True) == expected

    @pytest.mark.parametrize("label", ["N", "?", ""])
    def test_non_chords_pass_through(self, label: str) -> None:
        assert spell_chord_label(label, prefer_flats=True) == label

    def test_an_unrecognised_root_passes_through(self) -> None:
        assert spell_chord_label("Hm7", prefer_flats=True) == "Hm7"

    def test_without_the_preference_the_canonical_label_is_returned(self) -> None:
        assert spell_chord_label("A#m7/D#", prefer_flats=False) == "A#m7/D#"


class TestSpellKeyLabel:
    def test_a_flat_key_is_spelled_with_flats(self) -> None:
        assert spell_key_label("A#", "major") == "Bb major"
        assert spell_key_label("C#", "major") == "Db major"
        assert spell_key_label("D", "minor") == "D minor"

    def test_a_sharp_key_keeps_its_canonical_spelling(self) -> None:
        assert spell_key_label("C", "major") == "C major"
        assert spell_key_label("F#", "minor") == "F# minor"

    def test_an_unknown_key_is_unknown(self) -> None:
        assert spell_key_label(None, "major") == "unknown"
        assert spell_key_label("C", None) == "unknown"
        assert spell_key_label("C", "unknown") == "unknown"
