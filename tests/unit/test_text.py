"""``utils.text`` - the one place English agreement is decided (roadmap 63)."""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.utils.text import pluralize


class TestPluralize:
    def test_one_is_singular(self) -> None:
        assert pluralize(1, "segment") == "1 segment"
        assert pluralize(1, "word") == "1 word"

    def test_zero_and_many_are_plural(self) -> None:
        assert pluralize(0, "segment") == "0 segments"
        assert pluralize(2, "word") == "2 words"
        assert pluralize(41, "segment") == "41 segments"

    def test_a_negative_count_keeps_the_agreement_rule(self) -> None:
        assert pluralize(-1, "segment") == "-1 segments"

    @pytest.mark.parametrize("count", [1, 2])
    def test_the_number_is_never_reformatted(self, count: int) -> None:
        assert pluralize(count, "x").startswith(str(count))
