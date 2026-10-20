"""Canonical lyric models (roadmap sections 11, 109 and 110).

Engines may provide segment timestamps, word timestamps, or nothing at all.
Missing precision is represented by ``None`` and is never fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from song_chord_lyrics_analyzer.models.confidence import ConfidenceScore

__all__ = ["LyricSegment", "LyricSegmentKind", "LyricWord"]


class LyricSegmentKind(str, Enum):
    """What a lyric segment actually contains."""

    LYRICS = "lyrics"
    INSTRUMENTAL = "instrumental"
    NON_LEXICAL = "non_lexical"
    UNKNOWN = "unknown"


@dataclass
class LyricWord:
    """A single word (or non-lexical vocalisation) inside a lyric segment."""

    text: str
    start: float | None = None
    end: float | None = None
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore.unknown)
    source: str | None = None

    def __post_init__(self) -> None:
        if self.start is not None and self.start < 0:
            raise ValueError(f"word start must not be negative, got {self.start!r}")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError(
                f"word end ({self.end!r}) must not precede word start ({self.start!r})"
            )

    @property
    def has_timestamps(self) -> bool:
        """Whether both boundaries were supplied by the engine."""
        return self.start is not None and self.end is not None

    @property
    def duration(self) -> float | None:
        """Word duration in seconds when both boundaries are known."""
        if self.start is None or self.end is None:
            return None
        return self.end - self.start


@dataclass
class LyricSegment:
    """A lyric line (or a recognised instrumental region).

    Attributes:
        text: Segment text. Instrumental segments keep an explicit marker rather
            than fake words.
        start: Segment start in seconds, when known.
        end: Segment end in seconds, when known.
        words: Word-level annotations, possibly empty.
        confidence: Segment confidence as reported by the engine.
        language: BCP-47-ish language tag when detected.
        source: Engine that produced the segment.
        kind: Whether the segment contains lyrics, instrumental or non-lexical
            vocals.
    """

    text: str
    start: float | None = None
    end: float | None = None
    words: list[LyricWord] = field(default_factory=list)
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore.unknown)
    language: str | None = None
    source: str | None = None
    kind: LyricSegmentKind = LyricSegmentKind.LYRICS

    def __post_init__(self) -> None:
        if self.start is not None and self.start < 0:
            raise ValueError(f"segment start must not be negative, got {self.start!r}")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError(
                f"segment end ({self.end!r}) must not precede segment start ({self.start!r})"
            )

    @property
    def has_timestamps(self) -> bool:
        """Whether both boundaries were supplied by the engine."""
        return self.start is not None and self.end is not None

    @property
    def has_word_timestamps(self) -> bool:
        """Whether every word carries its own timestamps."""
        return bool(self.words) and all(word.has_timestamps for word in self.words)

    @property
    def duration(self) -> float | None:
        """Segment duration in seconds when both boundaries are known."""
        if self.start is None or self.end is None:
            return None
        return self.end - self.start
