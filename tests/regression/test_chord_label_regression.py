"""Regression tests for chord label handling.

The expectations live in a small JSON fixture
(``tests/fixtures/chord_labels.json``) so behaviour changes show up as an
explicit diff instead of a silent reinterpretation of engine output
(roadmap sections 13, 65 and 71).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from song_chord_lyrics_analyzer.models import ChordQuality
from song_chord_lyrics_analyzer.normalization import (
    parse_chord_label,
    transpose_chord_label,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "chord_labels.json"


def _cases() -> list[dict[str, object]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", _cases(), ids=lambda case: str(case["label"]))
def test_chord_labels_match_the_recorded_behaviour(case: dict[str, object]) -> None:
    parsed = parse_chord_label(str(case["label"]))

    assert parsed.root == case["root"]
    assert parsed.quality is ChordQuality(str(case["quality"]))
    assert parsed.bass == case["bass"]
    assert parsed.label == case["rendered"]

    if case["transposed"] is not None:
        semitones = int(case["semitones"])
        assert transpose_chord_label(str(case["label"]), semitones) == case["transposed"]


def test_fixture_covers_every_chord_quality_used_by_the_baseline() -> None:
    qualities = {str(case["quality"]) for case in _cases()}
    for quality in (
        ChordQuality.MAJOR.value,
        ChordQuality.MINOR.value,
        ChordQuality.NO_CHORD.value,
        ChordQuality.OTHER.value,
    ):
        assert quality in qualities
