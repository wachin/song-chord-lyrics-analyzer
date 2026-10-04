"""Chord segmentation metrics (roadmap section 44) against the mir_eval oracle.

``tests/fixtures/chord_metrics_oracle.json`` records the ``mir_eval`` (0.8.2)
values for ``chord.seg`` (MeanSeg), ``segment.detection`` (boundary hit rate at
0.5 s and 0.25 s) and ``segment.deviation`` (median change-point timing error)
over the committed GuitarSet takes; the dependency-free re-implementation must
reproduce them.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from song_chord_lyrics_analyzer.metrics import (
    chord_change_detection,
    segment_overlap,
    timing_error,
)

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"
ORACLE = json.loads((FIXTURE_DIR / "chord_metrics_oracle.json").read_text(encoding="utf-8"))
CSR = json.loads((FIXTURE_DIR / "csr_oracle.json").read_text(encoding="utf-8"))


class TestSegmentOverlapHandCases:
    def test_identical_segmentations(self) -> None:
        seg = [(0.0, 4.0, "C"), (4.0, 8.0, "G")]
        assert segment_overlap(seg, list(seg)) == 1.0

    def test_labels_are_ignored(self) -> None:
        ref = [(0.0, 4.0, "C"), (4.0, 8.0, "G")]
        hyp = [(0.0, 4.0, "Dm"), (4.0, 8.0, "A7")]
        assert segment_overlap(ref, hyp) == 1.0

    def test_missing_boundary_caps_at_under_segmentation(self) -> None:
        ref = [(0.0, 4.0, "C"), (4.0, 8.0, "G")]
        hyp = [(0.0, 8.0, "C")]
        # over = 1.0 (hyp adds no boundary inside ref), under = 1 - 4/8 = 0.5
        assert segment_overlap(ref, hyp) == 0.5

    def test_empty_sides_score_zero(self) -> None:
        seg = [(0.0, 4.0, "C")]
        assert segment_overlap([], seg) == 0.0
        assert segment_overlap(seg, []) == 0.0


class TestChordChangeDetectionHandCases:
    def test_identical_boundaries(self) -> None:
        seg = [(0.0, 4.0, "C"), (4.0, 8.0, "G")]
        assert chord_change_detection(seg, list(seg)) == {
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
        }

    def test_missing_boundary_lowers_recall(self) -> None:
        ref = [(0.0, 4.0, "C"), (4.0, 8.0, "G")]
        hyp = [(0.0, 8.0, "C")]
        result = chord_change_detection(ref, hyp)
        assert result["precision"] == 1.0
        assert result["recall"] == pytest.approx(2 / 3)
        assert result["f1"] == pytest.approx(0.8)

    def test_window_rejects_distant_boundary(self) -> None:
        ref = [(0.0, 4.0, "C"), (4.0, 8.0, "G")]
        hyp = [(0.0, 4.5, "C"), (4.5, 8.0, "G")]
        result = chord_change_detection(ref, hyp, window=0.25)
        assert result == {
            "precision": pytest.approx(2 / 3),
            "recall": pytest.approx(2 / 3),
            "f1": pytest.approx(2 / 3),
        }
        wider = chord_change_detection(ref, hyp, window=0.6)
        assert wider["f1"] == 1.0

    def test_trim_removes_track_markers(self) -> None:
        ref = [(0.0, 4.0, "C"), (4.0, 8.0, "G")]
        hyp = [(0.0, 8.0, "C")]
        assert chord_change_detection(ref, hyp, trim=True) == {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
        }


class TestTimingErrorHandCases:
    def test_median_nearest_boundary_distance(self) -> None:
        ref = [(0.0, 4.0, "C")]
        hyp = [(0.0, 4.2, "C")]
        assert timing_error(ref, hyp) == pytest.approx(
            {"reference_to_hypothesis": 0.1, "hypothesis_to_reference": 0.1}
        )

    def test_empty_sides_are_nan(self) -> None:
        result = timing_error([], [(0.0, 4.0, "C")])
        assert math.isnan(result["reference_to_hypothesis"])
        assert math.isnan(result["hypothesis_to_reference"])


class TestSegmentationOracle:
    def _segments(self, entry: dict) -> tuple[list[tuple], list[tuple]]:
        take = CSR["takes"][entry["take"]]
        ref = [tuple(obs) for obs in take["refs"][entry["ref_index"]]]
        hyp = [tuple(obs) for obs in take["hyp"]]
        return ref, hyp

    @pytest.mark.parametrize(
        "entry",
        ORACLE["segmentations"],
        ids=lambda e: f"{e['take']}-r{e['ref_index']}",
    )
    def test_matches_mir_eval(self, entry: dict) -> None:
        ref, hyp = self._segments(entry)
        expected = entry["expected"]
        assert segment_overlap(ref, hyp) == pytest.approx(expected["segment_overlap"], abs=1e-12)
        for window, expected_detection in expected["change_detection"].items():
            assert chord_change_detection(ref, hyp, window=float(window)) == pytest.approx(
                expected_detection, abs=1e-12
            )
        assert timing_error(ref, hyp) == pytest.approx(expected["timing_error"], abs=1e-12)

    def test_oracle_covers_both_annotations_and_windows(self) -> None:
        assert {entry["ref_index"] for entry in ORACLE["segmentations"]} == {0, 1}
        assert set(ORACLE["segmentations"][0]["expected"]["change_detection"]) == {"0.5", "0.25"}
