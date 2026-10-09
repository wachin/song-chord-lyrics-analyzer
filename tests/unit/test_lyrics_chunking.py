"""Long-audio windowing and reassembly for lyrics (roadmap section 25).

The measured finding is that the packaged Parakeet route cannot take a whole
song, so every lyrics engine has to window the audio itself. This file pins the
windowing arithmetic and the reassembly rule without a model, a download or a
sound card: the module is deliberately dependency-free, so the rules that decide
*where a word ends up on the song's clock* are tested directly.
"""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.engines.lyrics_chunking import (
    DEFAULT_CHUNK_SECONDS,
    Chunk,
    offset_segments,
    plan_chunks,
    reassemble,
)
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricWord
from song_chord_lyrics_analyzer.utils.errors import InputError


def _word(text: str, start: float | None, end: float | None = None) -> LyricWord:
    return LyricWord(text=text, start=start, end=end)


def _segment(
    text: str,
    start: float | None,
    end: float | None,
    words: list[LyricWord] | None = None,
) -> LyricSegment:
    return LyricSegment(text=text, start=start, end=end, words=words or [])


def _bounds(chunks: tuple[Chunk, ...]) -> list[tuple[float, float]]:
    return [(chunk.start, chunk.end) for chunk in chunks]


class TestPlanChunks:
    def test_the_measured_default_is_twenty_seconds(self) -> None:
        assert DEFAULT_CHUNK_SECONDS == 20.0

    def test_windows_tile_the_audio_and_the_last_one_is_shortened(self) -> None:
        chunks = plan_chunks(45.0)

        assert _bounds(chunks) == [(0.0, 20.0), (20.0, 40.0), (40.0, 45.0)]
        assert [chunk.index for chunk in chunks] == [0, 1, 2]
        assert chunks[-1].duration == pytest.approx(5.0)

    def test_audio_shorter_than_a_window_is_one_window(self) -> None:
        chunks = plan_chunks(5.0)

        assert _bounds(chunks) == [(0.0, 5.0)]

    def test_silence_plans_no_window_at_all(self) -> None:
        assert plan_chunks(0.0) == ()

    def test_an_overlap_moves_the_step_and_still_ends_at_the_end(self) -> None:
        chunks = plan_chunks(40.0, overlap_seconds=5.0)

        assert _bounds(chunks) == [(0.0, 20.0), (15.0, 35.0), (30.0, 40.0)]

    def test_a_custom_window_length_is_honoured(self) -> None:
        assert _bounds(plan_chunks(5.0, chunk_seconds=2.0)) == [
            (0.0, 2.0),
            (2.0, 4.0),
            (4.0, 5.0),
        ]

    def test_a_negative_duration_is_rejected(self) -> None:
        with pytest.raises(InputError, match=r"duration must be at least 0\.0"):
            plan_chunks(-1.0)

    def test_an_infinite_duration_is_rejected(self) -> None:
        with pytest.raises(InputError, match="duration must be finite"):
            plan_chunks(float("inf"))

    def test_a_non_numeric_duration_is_rejected(self) -> None:
        with pytest.raises(InputError, match="duration must be a number"):
            plan_chunks("10")  # type: ignore[arg-type]

    def test_a_boolean_is_not_a_duration(self) -> None:
        with pytest.raises(InputError, match="duration must be a number"):
            plan_chunks(True)  # type: ignore[arg-type]

    def test_a_zero_window_is_rejected(self) -> None:
        with pytest.raises(InputError, match="chunk_seconds must be positive"):
            plan_chunks(10.0, chunk_seconds=0.0)

    def test_an_overlap_as_long_as_the_window_is_rejected(self) -> None:
        with pytest.raises(InputError, match="must be smaller than chunk_seconds"):
            plan_chunks(10.0, chunk_seconds=20.0, overlap_seconds=20.0)

    def test_a_negative_overlap_is_rejected(self) -> None:
        with pytest.raises(InputError, match=r"overlap_seconds must be at least 0\.0"):
            plan_chunks(10.0, overlap_seconds=-1.0)


class TestChunk:
    def test_a_chunk_knows_its_length(self) -> None:
        assert Chunk(0, 1.5, 4.0).duration == pytest.approx(2.5)

    def test_a_backwards_chunk_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must not precede its start"):
            Chunk(0, 4.0, 1.0)

    def test_a_negative_index_is_refused(self) -> None:
        with pytest.raises(ValueError, match="index must not be negative"):
            Chunk(-1, 0.0, 1.0)

    def test_non_finite_bounds_are_refused(self) -> None:
        with pytest.raises(ValueError, match="bounds must be finite"):
            Chunk(0, 0.0, float("nan"))


class TestOffsetSegments:
    def test_segments_and_words_move_onto_the_song_clock(self) -> None:
        segment = _segment("hello", 0.0, 20.0, [_word("hello", 1.0, 2.0)])

        moved = offset_segments([segment], 20.0)

        assert moved[0].start == pytest.approx(20.0)
        assert moved[0].end == pytest.approx(40.0)
        assert moved[0].words[0].start == pytest.approx(21.0)
        assert moved[0].words[0].end == pytest.approx(22.0)

    def test_boundaries_the_model_did_not_report_stay_unknown(self) -> None:
        segment = _segment("hello", None, None, [_word("hello", None, None)])

        moved = offset_segments([segment], 20.0)

        assert moved[0].start is None
        assert moved[0].end is None
        assert moved[0].words[0].start is None
        assert moved[0].words[0].end is None

    def test_a_zero_offset_still_returns_a_new_list(self) -> None:
        segments = [_segment("hello", 0.0, 1.0)]

        moved = offset_segments(segments, 0.0)

        assert moved == segments
        assert moved is not segments


class TestReassemble:
    def test_a_second_window_lands_after_the_first_on_the_song_clock(self) -> None:
        chunks = plan_chunks(30.0)
        first = _segment("first", 0.0, 20.0, [_word("first", 0.0)])
        second = _segment("second", 0.0, 10.0, [_word("second", 0.5)])

        assembled = reassemble([[first], [second]], chunks)

        assert [segment.text for segment in assembled] == ["first", "second"]
        assert assembled[1].start == pytest.approx(20.0)
        assert assembled[1].words[0].start == pytest.approx(20.5)

    def test_an_empty_window_contributes_nothing(self) -> None:
        chunks = plan_chunks(40.0)

        transcribed = [_segment("text", 0.0, 20.0, [_word("text", 1.0)])]

        assembled = reassemble([transcribed, []], chunks)

        assert len(assembled) == 1

    def test_the_earlier_window_wins_on_an_overlap(self) -> None:
        """The documented rule: no similarity heuristic, the first hearing stays."""
        chunks = plan_chunks(40.0, overlap_seconds=5.0)
        first = _segment("a b", 0.0, 20.0, [_word("a", 0.0, 5.0), _word("b", 18.0, 19.5)])
        repeated = _segment("b c", 0.0, 20.0, [_word("b", 3.0, 4.5), _word("c", 5.5, 6.5)])

        assembled = reassemble([[first], [repeated], []], chunks)

        assert [word.text for word in assembled[1].words] == ["c"]
        assert assembled[1].words[0].start == pytest.approx(20.5)

    def test_a_segment_left_without_words_is_dropped_with_them(self) -> None:
        chunks = plan_chunks(40.0, overlap_seconds=5.0)
        first = _segment("a", 0.0, 20.0, [_word("a", 0.0, 5.0)])
        repeated = _segment("a", 0.0, 5.0, [_word("a", 1.0, 2.0)])

        assembled = reassemble([[first], [repeated], []], chunks)

        assert [segment.text for segment in assembled] == ["a"]

    def test_a_segment_without_words_survives(self) -> None:
        chunks = plan_chunks(25.0)
        text_only = _segment("no word timestamps", 0.0, 20.0)

        assembled = reassemble([[text_only], []], chunks)

        assert [segment.text for segment in assembled] == ["no word timestamps"]

    def test_mismatched_window_and_chunk_counts_are_a_bug(self) -> None:
        with pytest.raises(ValueError, match="2 transcribing windows for 3 chunks"):
            reassemble([[], []], plan_chunks(45.0))

    def test_no_windows_means_no_lyrics(self) -> None:
        assert reassemble([], plan_chunks(0.0)) == ()
