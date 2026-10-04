"""Lyrics metrics (roadmap section 44) against the jiwer oracle.

``tests/fixtures/lyrics_oracle.json`` records ``jiwer`` 4.0.0 (identity
transforms) WER and CER for deterministic perturbations of the committed
vocadito lyric references; the dependency-free implementation must reproduce
them. The timestamp metric has no external reference and is covered by hand
cases.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from song_chord_lyrics_analyzer.metrics import (
    character_error_rate,
    lyric_text,
    normalize_text,
    timed_words,
    word_error_rate,
    word_timestamp_error,
)
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricWord

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"
ORACLE = json.loads((FIXTURE_DIR / "lyrics_oracle.json").read_text(encoding="utf-8"))


class TestNormalizeText:
    def test_case_and_punctuation_are_folded(self) -> None:
        assert normalize_text("  Héllo,   WORLD!! ") == "héllo world"

    def test_punctuation_between_words_becomes_a_space(self) -> None:
        assert normalize_text("rock'n'roll") == "rock n roll"

    def test_whitespace_is_collapsed(self) -> None:
        assert normalize_text("a\t b\n\nc") == "a b c"


class TestWordErrorRate:
    def test_identical_text_scores_zero(self) -> None:
        assert word_error_rate("a b c", "a b c") == 0.0

    def test_one_substitution_over_three_words(self) -> None:
        assert word_error_rate("a b c", "a x c") == 1 / 3

    def test_deletion_is_charged_against_the_reference(self) -> None:
        assert word_error_rate("a b c", "a b") == 1 / 3

    def test_insertion_is_charged_against_the_reference(self) -> None:
        assert word_error_rate("a b", "a b c") == 0.5

    def test_transposition_costs_two_edits(self) -> None:
        assert word_error_rate("a b c", "b a c") == 2 / 3

    def test_empty_reference_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one word"):
            word_error_rate("   ", "anything")


class TestCharacterErrorRate:
    def test_one_character_substitution(self) -> None:
        assert character_error_rate("abc", "abd") == 1 / 3

    def test_spaces_between_words_count(self) -> None:
        # "ab cd" has 5 characters; dropping "cd" removes three of them.
        assert character_error_rate("ab cd", "ab") == 3 / 5

    def test_empty_reference_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one character"):
            character_error_rate("!!!", "x")


class TestWordTimestampError:
    def test_median_and_mean_over_shared_words(self) -> None:
        reference = [("a", 0.0), ("b", 1.0)]
        hypothesis = [("a", 0.1), ("b", 0.9)]
        assert word_timestamp_error(reference, hypothesis) == pytest.approx(
            {"median_seconds": 0.1, "mean_seconds": 0.1, "matched_words": 2.0}
        )

    def test_missing_word_is_aligned_away(self) -> None:
        reference = [("a", 0.0), ("b", 1.0), ("c", 2.0)]
        hypothesis = [("a", 0.05), ("c", 2.1)]
        result = word_timestamp_error(reference, hypothesis)
        assert result["matched_words"] == 2.0
        assert result["median_seconds"] == pytest.approx(0.075)

    def test_inserted_word_does_not_line_up(self) -> None:
        reference = [("a", 0.0), ("b", 1.0)]
        hypothesis = [("um", 0.0), ("a", 0.2), ("b", 1.0)]
        result = word_timestamp_error(reference, hypothesis)
        assert result["matched_words"] == 2.0
        assert result["median_seconds"] == pytest.approx(0.1)

    def test_no_shared_word_is_nan(self) -> None:
        result = word_timestamp_error([("a", 0.0)], [("z", 0.0)])
        assert math.isnan(result["median_seconds"])
        assert math.isnan(result["mean_seconds"])
        assert result["matched_words"] == 0.0


class TestLyricsOracle:
    @pytest.mark.parametrize("case", ORACLE["cases"], ids=lambda c: c["id"])
    def test_matches_jiwer(self, case: dict) -> None:
        assert word_error_rate(case["reference"], case["hypothesis"]) == pytest.approx(
            case["expected"]["word_error_rate"], abs=1e-12
        )
        assert character_error_rate(case["reference"], case["hypothesis"]) == pytest.approx(
            case["expected"]["character_error_rate"], abs=1e-12
        )


class TestLyricsAdapters:
    def test_lyric_text_joins_segments(self) -> None:
        segments = [LyricSegment(text="hola"), LyricSegment(text="mundo")]
        assert lyric_text(segments) == "hola mundo"

    def test_lyric_text_skips_empty_segments(self) -> None:
        segments = [LyricSegment(text="hola"), LyricSegment(text="")]
        assert lyric_text(segments) == "hola"

    def test_timed_words_drop_words_without_a_start(self) -> None:
        words = [LyricWord(text="a", start=0.0, end=1.0), LyricWord(text="um")]
        assert timed_words(words) == [("a", 0.0)]

    def test_segments_feed_the_text_metrics(self) -> None:
        reference = [LyricSegment(text="hola mundo")]
        hypothesis = [LyricSegment(text="hola Mundo!")]
        assert word_error_rate(lyric_text(reference), lyric_text(hypothesis)) == 0.0
