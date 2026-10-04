"""Key metrics (roadmap section 44) against the mir_eval oracle.

``tests/fixtures/key_oracle.json`` records ``mir_eval.key.weighted_score`` (0.8.2)
for every ordered pair of GuitarSet's 19 distinct annotated keys; the
dependency-free re-implementation must reproduce the relation and the score, and
the aggregate views build on those.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from song_chord_lyrics_analyzer.metrics import (
    exact_key_accuracy,
    key_labels,
    key_relation,
    key_relation_counts,
    relative_key_error,
    same_key,
    weighted_key_score,
)
from song_chord_lyrics_analyzer.models.music import KeyEstimate, KeyMode

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"
ORACLE = json.loads((FIXTURE_DIR / "key_oracle.json").read_text(encoding="utf-8"))


class TestKeyRelationHandCases:
    def test_exact_key(self) -> None:
        assert key_relation("C major", "C major") == "exact"

    def test_enharmonic_spellings_are_equal(self) -> None:
        assert key_relation("C# major", "Db major") == "exact"
        assert same_key("F# minor", "Gb minor") is True

    def test_fifth_above(self) -> None:
        assert key_relation("C major", "G major") == "fifth"

    def test_relative_both_directions(self) -> None:
        assert key_relation("C major", "A minor") == "relative"
        assert key_relation("A minor", "C major") == "relative"

    def test_parallel(self) -> None:
        assert key_relation("C major", "C minor") == "parallel"

    def test_unrelated(self) -> None:
        assert key_relation("C major", "D major") == "other"

    def test_unknown_is_never_a_match(self) -> None:
        assert key_relation("unknown", "C major") == "unknown"
        assert key_relation("C major", "unknown") == "unknown"
        assert key_relation("unknown", "unknown") == "unknown"
        assert key_relation("C major", "X") == "unknown"
        assert same_key("unknown", "unknown") is False

    def test_mode_case_is_ignored_like_mir_eval(self) -> None:
        assert key_relation("c major", "C major") == "exact"

    def test_malformed_label_raises(self) -> None:
        with pytest.raises(ValueError, match="key must look like"):
            key_relation("Cmajor", "C major")


class TestWeightedKeyScore:
    def test_weights_follow_the_relationship(self) -> None:
        assert weighted_key_score("C major", "C major") == 1.0
        assert weighted_key_score("C major", "G major") == 0.5
        assert weighted_key_score("C major", "A minor") == 0.3
        assert weighted_key_score("C major", "C minor") == 0.2
        assert weighted_key_score("C major", "D major") == 0.0
        assert weighted_key_score("C major", "unknown") == 0.0


class TestAggregateViews:
    def test_exact_accuracy_counts_only_exact(self) -> None:
        references = ["C major", "G major", "A minor", "C major"]
        estimates = ["C major", "D major", "A minor", "unknown"]
        assert exact_key_accuracy(references, estimates) == 0.5

    def test_relative_error_counts_only_relative(self) -> None:
        references = ["C major", "G major", "A minor", "C major"]
        estimates = ["A minor", "G major", "C major", "C minor"]
        # A minor (relative), exact, relative, parallel -> 2 / 4
        assert relative_key_error(references, estimates) == 0.5

    def test_empty_input_scores_zero(self) -> None:
        assert exact_key_accuracy([], []) == 0.0
        assert relative_key_error([], []) == 0.0

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="as many references"):
            exact_key_accuracy(["C major"], [])

    def test_relation_counts_include_every_relation(self) -> None:
        counts = key_relation_counts(["C major", "C major"], ["C major", "A minor"])
        assert counts == {
            "exact": 1,
            "fifth": 0,
            "relative": 1,
            "parallel": 0,
            "other": 0,
            "unknown": 0,
        }


class TestKeyOracle:
    @pytest.mark.parametrize(
        "case",
        ORACLE["keys"],
        ids=lambda c: f"{c['reference']}->{c['estimate']}",
    )
    def test_matches_mir_eval(self, case: dict) -> None:
        assert key_relation(case["reference"], case["estimate"]) == case["relation"]
        assert weighted_key_score(case["reference"], case["estimate"]) == case["weighted_score"]

    def test_oracle_covers_every_distinct_key(self) -> None:
        assert len(ORACLE["distinct_keys"]) == 19
        assert len(ORACLE["keys"]) == 19 * 19


class TestKeyAdapters:
    def test_key_labels_from_estimates(self) -> None:
        estimates = [
            KeyEstimate(tonic="C", mode=KeyMode.MAJOR),
            KeyEstimate(tonic="F#", mode=KeyMode.MINOR),
            KeyEstimate(),
        ]
        assert key_labels(estimates) == ["C major", "F# minor", "unknown"]

    def test_estimates_feed_the_metrics(self) -> None:
        references = [KeyEstimate(tonic="C", mode=KeyMode.MAJOR)]
        estimates = [KeyEstimate(tonic="A", mode=KeyMode.MINOR)]
        assert exact_key_accuracy(key_labels(references), key_labels(estimates)) == 0.0
        assert relative_key_error(key_labels(references), key_labels(estimates)) == 1.0
