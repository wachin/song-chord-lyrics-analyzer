"""Canonical-model adapters for the chord metrics (roadmap section 44).

The metrics score plain label sequences and timed triples; a pipeline carries
:class:`~song_chord_lyrics_analyzer.models.music.ChordEvent` objects. These
tests pin both the extraction and the no-invention rule: a chord whose end
cannot be determined raises instead of guessing a boundary.
"""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.metrics import (
    chord_change_detection,
    chord_labels,
    chord_segments,
    evaluate,
    segment_overlap,
    timing_error,
)
from song_chord_lyrics_analyzer.models.music import ChordEvent, ChordQuality


def _major(start: float, end: float | None, root: str) -> ChordEvent:
    return ChordEvent(start=start, end=end, root=root, quality=ChordQuality.MAJOR)


def _dominant7(start: float, end: float | None, root: str) -> ChordEvent:
    return ChordEvent(start=start, end=end, root=root, quality=ChordQuality.DOMINANT7)


class TestChordLabels:
    def test_labels_follow_event_order(self) -> None:
        events = [_major(0.0, 4.0, "C"), _major(4.0, 8.0, "G")]
        assert chord_labels(events) == ["C", "G"]

    def test_silence_and_unknown_survive(self) -> None:
        events = [
            ChordEvent.silence(0.0, 4.0),
            ChordEvent(start=4.0, end=8.0),
            _major(8.0, 12.0, "F#"),
        ]
        assert chord_labels(events) == ["N", "?", "F#"]

    def test_empty_sequence(self) -> None:
        assert chord_labels([]) == []


class TestChordSegments:
    def test_explicit_ends_are_used(self) -> None:
        events = [_major(0.0, 4.0, "C"), _major(4.0, 8.0, "G")]
        assert chord_segments(events) == [(0.0, 4.0, "C"), (4.0, 8.0, "G")]

    def test_missing_end_is_filled_from_next_start(self) -> None:
        events = [_major(0.0, None, "C"), _major(4.0, None, "G"), _major(8.0, None, "D")]
        assert chord_segments(events, end=12.0) == [
            (0.0, 4.0, "C"),
            (4.0, 8.0, "G"),
            (8.0, 12.0, "D"),
        ]

    def test_last_end_falls_back_to_track_end(self) -> None:
        events = [_major(0.0, 4.0, "C"), _major(4.0, None, "G")]
        assert chord_segments(events, end=9.5) == [(0.0, 4.0, "C"), (4.0, 9.5, "G")]

    def test_explicit_end_ignored_when_last_chord_has_one(self) -> None:
        events = [_major(0.0, 4.0, "C"), _major(4.0, 8.0, "G")]
        assert chord_segments(events, end=99.0) == [(0.0, 4.0, "C"), (4.0, 8.0, "G")]

    def test_empty_sequence(self) -> None:
        assert chord_segments([], end=10.0) == []

    def test_undetermined_last_end_raises(self) -> None:
        events = [_major(0.0, 4.0, "C"), _major(4.0, None, "G")]
        with pytest.raises(ValueError, match="cannot determine the end"):
            chord_segments(events)

    def test_reversed_track_end_raises(self) -> None:
        events = [_major(10.0, None, "C")]
        with pytest.raises(ValueError, match="reversed"):
            chord_segments(events, end=5.0)

    def test_overlapping_events_raise(self) -> None:
        events = [_major(0.0, 4.0, "C"), _major(2.0, 8.0, "G")]
        with pytest.raises(ValueError, match="overlap"):
            chord_segments(events)

    def test_inferred_end_before_start_raises(self) -> None:
        events = [_major(4.0, None, "C"), _major(2.0, None, "G")]
        with pytest.raises(ValueError, match="reversed"):
            chord_segments(events, end=8.0)

    def test_silence_keeps_its_n_label(self) -> None:
        events = [ChordEvent.silence(0.0, 4.0), _major(4.0, 8.0, "C")]
        assert chord_segments(events) == [(0.0, 4.0, "N"), (4.0, 8.0, "C")]


class TestAdapterFeedsTheMetrics:
    def test_labels_drive_evaluate(self) -> None:
        ref = [_major(0.0, 4.0, "C"), _major(4.0, 8.0, "G")]
        hyp = [_major(0.0, 4.0, "C"), _dominant7(4.0, 8.0, "G")]
        result = evaluate(chord_labels(ref), chord_labels(hyp))
        # The seventh is exact-mismatched but shares G's root.
        assert result["exact"] == {"precision": 0.5, "recall": 0.5, "f1": 0.5}
        assert result["root"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    def test_segments_drive_boundary_metrics(self) -> None:
        ref = [_major(0.0, 4.0, "C"), _major(4.0, 8.0, "G")]
        same = [_major(0.0, 4.0, "C"), _major(4.0, 8.0, "G")]
        merged = [_major(0.0, 8.0, "C")]

        assert segment_overlap(chord_segments(ref), chord_segments(same)) == 1.0
        assert segment_overlap(chord_segments(ref), chord_segments(merged, end=8.0)) == 0.5
        assert chord_change_detection(chord_segments(ref), chord_segments(same)) == {
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
        }

    def test_segments_drive_timing_error(self) -> None:
        # One chord, so both boundary sets are {0, end} and the 0.2 s shift
        # shows up in both directions as a 0.1 s median.
        ref = [_major(0.0, 4.0, "C")]
        hyp = [_major(0.0, 4.2, "C")]
        assert timing_error(chord_segments(ref), chord_segments(hyp)) == pytest.approx(
            {"reference_to_hypothesis": 0.1, "hypothesis_to_reference": 0.1}
        )
