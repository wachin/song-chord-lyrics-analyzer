"""Chord metrics (roadmap section 44) against the NumPy harness oracle.

``tests/fixtures/chord_metrics_oracle.json`` records the expected ``align`` and
``evaluate`` results produced by the original NumPy harness over the committed
GuitarSet takes; the pure-Python library implementation must reproduce them
exactly. The sequences themselves are rebuilt from
``tests/fixtures/csr_oracle.json`` (Harte labels decoded with the package's own
:func:`harte_to_label` / :func:`triad_reduce`), so the reconstruction is pinned
too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from song_chord_lyrics_analyzer.evaluation import harte_to_label, mirex_equal, triad_reduce
from song_chord_lyrics_analyzer.metrics import (
    align,
    duration_csr,
    evaluate,
    same_quality,
    same_root,
)

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"
ORACLE = json.loads((FIXTURE_DIR / "chord_metrics_oracle.json").read_text(encoding="utf-8"))
CSR = json.loads((FIXTURE_DIR / "csr_oracle.json").read_text(encoding="utf-8"))


def _predicates() -> dict[str, object]:
    return {
        "exact": lambda a, b: a == b,
        "root": same_root,
        "quality": same_quality,
        "mirex": mirex_equal,
    }


class TestSameRootQuality:
    def test_same_root_ignores_quality(self) -> None:
        assert same_root("C7", "Cmaj7") is True
        assert same_root("C", "D") is False

    def test_no_chord_has_no_root(self) -> None:
        assert same_root("N", "N") is False
        assert same_root("N", "C") is False

    def test_same_quality_ignores_root(self) -> None:
        assert same_quality("C7", "D7") is True
        assert same_quality("C7", "Cmaj7") is False


class TestAlignHandCases:
    def test_both_empty_is_perfect(self) -> None:
        assert align([], [], lambda a, b: a == b) == {
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "matches": 0.0,
            "score": 0.0,
        }

    def test_identical_sequences(self) -> None:
        result = align(["C", "G", "Am"], ["C", "G", "Am"], lambda a, b: a == b)
        assert result["f1"] == 1.0
        assert result["matches"] == 3.0

    def test_empty_reference_has_zero_recall(self) -> None:
        result = align([], ["C", "G"], lambda a, b: a == b)
        assert result["precision"] == 0.0
        assert result["recall"] == 0.0
        assert result["f1"] == 0.0

    def test_partial_overlap(self) -> None:
        result = align(["C", "G", "Am"], ["C", "F", "Am"], lambda a, b: a == b)
        # Two matches survive the alignment: C--C and Am--Am.
        assert result["matches"] == 2.0
        assert result["precision"] == pytest.approx(2 / 3)
        assert result["recall"] == pytest.approx(2 / 3)

    def test_empty_hypothesis_has_zero_precision(self) -> None:
        result = align(["C", "G"], [], lambda a, b: a == b)
        assert result["precision"] == 0.0
        assert result["recall"] == 0.0


class TestAlignOracle:
    @pytest.mark.parametrize("case", ORACLE["alignments"], ids=lambda c: c["name"])
    def test_matches_harness(self, case: dict) -> None:
        predicate = _predicates()[case["predicate"]]
        got = align(
            case["ref"],
            case["hyp"],
            predicate,
            gap_cost=case["gap_cost"],
            mismatch_cost=case["mismatch_cost"],
        )
        assert got == case["expected"]


class TestEvaluateHandCases:
    def test_identical_perfect(self) -> None:
        result = evaluate(["C", "G", "Am"], ["C", "G", "Am"])
        assert result["exact"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
        assert result["multiset_f1"] == 1.0
        assert result["palette_f1"] == 1.0
        assert result["hyp_chords"] == 3

    def test_empty_pair_is_perfect_but_no_chords(self) -> None:
        result = evaluate([], [])
        assert result["exact"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
        assert result["multiset_f1"] == 1.0
        assert result["palette_f1"] == 1.0
        assert result["hyp_chords"] == 0

    def test_hyp_chords_skips_no_chord(self) -> None:
        result = evaluate(["C"], ["C", "N", "N"])
        assert result["hyp_chords"] == 1

    def test_no_chord_vs_chord_is_no_match(self) -> None:
        result = evaluate(["N"], ["C"])
        assert result["exact"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    def test_multiset_is_order_insensitive(self) -> None:
        result = evaluate(["C", "G", "C"], ["C", "C", "G"])
        # Alignment is order-sensitive (only one C can be paired in place),
        # while the bag/palette views do not care about order.
        assert result["exact"]["f1"] < 1.0
        assert result["multiset_f1"] == 1.0
        assert result["palette_f1"] == 1.0


class TestEvaluateOracle:
    def _sequences(self, entry: dict) -> tuple[list[str], list[str]]:
        take = CSR["takes"][entry["take"]]
        raw = [harte_to_label(value) for _, _, value in take["refs"][entry["ref_index"]]]
        ref = [triad_reduce([label])[0] for label in raw] if entry["view"] == "triads" else raw
        hyp = [label for _, _, label in take["hyp"]]
        return ref, hyp

    @pytest.mark.parametrize(
        "entry",
        ORACLE["evaluations"],
        ids=lambda e: f"{e['take']}-r{e['ref_index']}-{e['view']}",
    )
    def test_matches_harness(self, entry: dict) -> None:
        ref, hyp = self._sequences(entry)
        assert evaluate(ref, hyp) == entry["expected"]

    def test_oracle_covers_both_views(self) -> None:
        views = {entry["view"] for entry in ORACLE["evaluations"]}
        assert views == {"raw", "triads"}

    def test_provenance_is_recorded(self) -> None:
        assert "GuitarSet" in ORACLE["provenance"]["dataset"]
        assert "CC BY 4.0" in ORACLE["provenance"]["dataset"]


class TestDurationCsrReExport:
    def test_re_exported_from_metrics(self) -> None:
        ref = [(0.0, 6.0, "C"), (6.0, 16.0, "G")]
        hyp = [(0.0, 6.0, "C"), (6.0, 11.0, "G"), (11.0, 16.0, "Am")]
        assert duration_csr(ref, hyp)["csr"] == pytest.approx(11 / 16)
