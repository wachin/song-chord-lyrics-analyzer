"""Unit tests for timestamp helpers."""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.utils.time import (
    format_duration,
    format_timestamp,
    parse_timestamp,
)


class TestFormatTimestamp:
    def test_unknown(self) -> None:
        assert format_timestamp(None) == "unknown"

    def test_millisecond_precision(self) -> None:
        assert format_timestamp(0) == "00:00:00.000"
        assert format_timestamp(1.5) == "00:00:01.500"
        assert format_timestamp(3725.321) == "01:02:05.321"

    def test_negative_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_timestamp(-0.001)


class TestFormatDuration:
    def test_compact_format(self) -> None:
        assert format_duration(0) == "0:00"
        assert format_duration(90.4) == "1:30"
        assert format_duration(3725) == "1:02:05"

    def test_unknown(self) -> None:
        assert format_duration(None) == "unknown"

    def test_negative_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_duration(-1)


class TestParseTimestamp:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("0", 0.0),
            ("90", 90.0),
            ("1:30", 90.0),
            ("01:02:05.500", 3725.5),
            ("  2:00  ", 120.0),
        ],
    )
    def test_valid(self, text: str, expected: float) -> None:
        assert parse_timestamp(text) == pytest.approx(expected)

    @pytest.mark.parametrize("text", ["", "   ", "a:b", "1:2:3:4", "-5"])
    def test_invalid(self, text: str) -> None:
        with pytest.raises(ValueError):
            parse_timestamp(text)
