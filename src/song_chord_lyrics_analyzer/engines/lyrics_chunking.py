"""Windowing and reassembly for long-audio lyric transcription (roadmap 25).

Measured in ``docs/ENGINE_COMPARISON.md``: the packaged ONNX Parakeet route
cannot take a whole song. ``recognize()`` on a 272 s file returned 8 garbled
words, and the upstream ``with_vad(silero)`` long-audio route returned nothing
at all - a *speech* VAD does not treat singing as speech. Only fixed windows
worked (67 words, 10 of 12 known lines, real-time factor 0.19).

This module owns that windowing. It is deliberately free of numpy, of the model
and of the engine: it plans windows over a duration, shifts the timestamps a
model produced *inside* one window onto the song's own clock, and joins the
per-window results into one lyric list. The whole reassembly rule is therefore
testable without a model, a download or a sound card.

Two rules are worth stating because they are choices, not arithmetic:

* **An earlier window wins.** When windows overlap, a word that starts before
  everything already kept is dropped as a repeat of audio the previous window
  heard first. This is deterministic and needs no similarity heuristic, but it
  also means a word *clipped* at a window edge can still be lost: overlap makes
  the seam audible twice, it does not currently repair it. Nothing here
  pretends otherwise.
* **A window is a segment.** One window produces at most one lyric segment, and
  the segment spans the window it was transcribed from - not a detected end of
  the line. Word boundaries come from the model's own token timestamps, and a
  line's real end is not invented from them.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace

from song_chord_lyrics_analyzer.models.lyrics import LyricSegment
from song_chord_lyrics_analyzer.utils.errors import InputError

__all__ = [
    "DEFAULT_CHUNK_SECONDS",
    "Chunk",
    "offset_segments",
    "plan_chunks",
    "reassemble",
]

#: Window length the section 25 investigation measured on a real 272 s song.
DEFAULT_CHUNK_SECONDS = 20.0


@dataclass(frozen=True)
class Chunk:
    """One window of audio handed to a lyrics engine on its own."""

    index: int
    start: float
    end: float

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError(f"chunk index must not be negative, got {self.index!r}")
        if not math.isfinite(self.start) or not math.isfinite(self.end):
            raise ValueError(f"chunk bounds must be finite, got {self.start!r}-{self.end!r}")
        if self.end < self.start:
            raise ValueError(
                f"chunk end ({self.end!r}) must not precede its start ({self.start!r})"
            )

    @property
    def duration(self) -> float:
        """Window length in seconds."""
        return self.end - self.start


def _checked_seconds(value: float, name: str, *, minimum: float) -> float:
    """Validate one non-negative, finite number of seconds."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{name} must be a number of seconds, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise InputError(f"{name} must be finite, got {value!r}")
    if number < minimum:
        raise InputError(f"{name} must be at least {minimum}, got {number!r}")
    return number


def plan_chunks(
    duration: float,
    *,
    chunk_seconds: float = DEFAULT_CHUNK_SECONDS,
    overlap_seconds: float = 0.0,
) -> tuple[Chunk, ...]:
    """Cover ``duration`` seconds of audio with fixed, non-empty windows.

    Windows are laid out from the start of the audio with a step of
    ``chunk_seconds - overlap_seconds``; the last one is shortened to the end of
    the audio instead of being padded, so no window claims audio that is not
    there, and a window that would only repeat audio an earlier window already
    covered is not planned at all. A duration of ``0`` plans **no** window:
    silence is not something to transcribe.

    Args:
        duration: Length of the audio in seconds.
        chunk_seconds: Window length. The measured default is 20 s.
        overlap_seconds: How much neighbouring windows share. ``0`` tiles the
            audio exactly.

    Returns:
        One :class:`Chunk` per window, in playback order.

    Raises:
        InputError: When ``duration`` is negative or not finite, when
            ``chunk_seconds`` is not positive, or when ``overlap_seconds`` is
            negative or not smaller than ``chunk_seconds``.
    """
    total = _checked_seconds(duration, "duration", minimum=0.0)
    window = _checked_seconds(chunk_seconds, "chunk_seconds", minimum=0.0)
    if window <= 0.0:
        raise InputError(f"chunk_seconds must be positive, got {window!r}")
    overlap = _checked_seconds(overlap_seconds, "overlap_seconds", minimum=0.0)
    if overlap >= window:
        raise InputError(
            f"overlap_seconds ({overlap!r}) must be smaller than chunk_seconds ({window!r})",
            hint="An overlap as long as the window would never advance.",
        )
    if total == 0.0:
        return ()

    step = window - overlap
    chunks: list[Chunk] = []
    index = 0
    start = 0.0
    covered_end: float | None = None
    while start < total:
        end = min(start + window, total)
        # A window that lies inside audio already covered adds nothing but a
        # repeat request to the model: once the tiling reaches the end, stop.
        if covered_end is not None and end <= covered_end:
            break
        chunks.append(Chunk(index, start, end))
        index += 1
        covered_end = end
        start = index * step
    return tuple(chunks)


def _shifted(value: float | None, offset: float) -> float | None:
    """Move one optional timestamp by ``offset`` seconds."""
    return None if value is None else value + offset


def offset_segments(
    segments: Sequence[LyricSegment],
    offset: float,
) -> list[LyricSegment]:
    """Return ``segments`` moved ``offset`` seconds later.

    Segment and word boundaries the engine did not report stay ``None``; only
    the timestamps that exist are moved.
    """
    if offset == 0.0:
        return list(segments)
    moved: list[LyricSegment] = []
    for segment in segments:
        segment_start = _shifted(segment.start, offset)
        segment_end = _shifted(segment.end, offset)
        if segment_start is not None and segment_start < 0.0:
            raise InputError(f"shifting by {offset!r} puts a segment before 0 s")
        words = [
            replace(
                word,
                start=_shifted(word.start, offset),
                end=_shifted(word.end, offset),
            )
            for word in segment.words
        ]
        moved.append(replace(segment, start=segment_start, end=segment_end, words=words))
    return moved


def _covered(start: float | None, frontier: float | None) -> bool:
    """Whether something starting at ``start`` was already kept."""
    if start is None or frontier is None:
        return False
    return start < frontier


def _window_end(segments: Sequence[LyricSegment], end: float) -> float:
    """Where the audio covered by one window's output actually ends."""
    ends = [end]
    for segment in segments:
        for word in segment.words:
            if word.end is not None:
                ends.append(word.end)
            elif word.start is not None:
                ends.append(word.start)
        if segment.end is not None:
            ends.append(segment.end)
    return max(ends)


def reassemble(
    chunk_segments: Sequence[Sequence[LyricSegment]],
    chunks: Sequence[Chunk],
) -> tuple[LyricSegment, ...]:
    """Join per-window transcription into one lyric list on the song's clock.

    Every segment is moved from its window's local time onto the file's own
    timeline, words the previous window already heard are dropped, and a
    segment left with no word of its own is dropped with them.

    Args:
        chunk_segments: One entry per window, in the same order as ``chunks``.
            An entry may be empty when the window produced no text.
        chunks: The windows those segments were transcribed from.

    Returns:
        The lyric segments in playback order.

    Raises:
        ValueError: When the two sequences do not line up one to one.
    """
    if len(chunk_segments) != len(chunks):
        raise ValueError(f"got {len(chunk_segments)} transcribing windows for {len(chunks)} chunks")
    assembled: list[LyricSegment] = []
    frontier: float | None = None
    for chunk, segments in zip(chunks, chunk_segments, strict=True):
        shifted = offset_segments(segments, chunk.start)
        for segment in shifted:
            kept = [word for word in segment.words if not _covered(word.start, frontier)]
            if segment.words and not kept:
                continue
            assembled.append(replace(segment, words=kept))
        if shifted:
            window_end = _window_end(shifted, chunk.start + chunk.duration)
            frontier = window_end if frontier is None else max(frontier, window_end)
    return tuple(assembled)
