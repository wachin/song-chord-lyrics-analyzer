"""Engine interfaces (roadmap sections 8, 14, 15 and 58-59).

The rest of the application depends on these protocols only. Concrete engines
(Chordino, Madmom, a chroma baseline, Whisper variants, ...) are adapters that
can be registered, compared and replaced without touching the CLI or the GUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from song_chord_lyrics_analyzer.models.analysis import EngineInfo, EngineResult

__all__ = [
    "BaseEngine",
    "BeatEngine",
    "ChordAnalysisOptions",
    "ChordEngine",
    "EngineKind",
    "KeyEngine",
    "LyricsEngine",
    "LyricsOptions",
    "StemSeparationOptions",
    "StemSeparationEngine",
    "TempoEngine",
]


class EngineKind(str, Enum):
    """Which analysis task an engine performs."""

    CHORDS = "chords"
    LYRICS = "lyrics"
    BEATS = "beats"
    KEY = "key"
    TEMPO = "tempo"
    STEMS = "stems"
    NOTES = "notes"


@dataclass
class ChordAnalysisOptions:
    """Options passed to a chord engine.

    Attributes:
        start: Restrict analysis to a time range starting here (seconds).
        end: Restrict analysis to a time range ending here (seconds).
        vocabulary_phase: Chord vocabulary phase to allow (roadmap section 13).
        minimum_duration: Minimum chord duration in seconds (0 disables it).
        extra: Engine-specific options, forwarded verbatim.
    """

    start: float | None = None
    end: float | None = None
    vocabulary_phase: int = 1
    minimum_duration: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class LyricsOptions:
    """Options passed to a lyrics engine.

    Attributes:
        language: Force a language (``None`` = automatic detection).
        word_timestamps: Whether word-level timestamps are requested.
        start: Restrict analysis to a time range starting here (seconds).
        end: Restrict analysis to a time range ending here (seconds).
        extra: Engine-specific options, forwarded verbatim.
    """

    language: str | None = None
    word_timestamps: bool = True
    start: float | None = None
    end: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class StemSeparationOptions:
    """Options passed to a stem separation engine."""

    stems: tuple[str, ...] = ("vocals", "drums", "bass", "other")
    output_dir: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class BaseEngine(Protocol):
    """Common contract of every engine adapter.

    Engines must be honest about availability: :meth:`is_available` reports
    whether the optional dependency or model is actually present, and
    :meth:`engine_info` reports the version that will be recorded as provenance.
    """

    #: Stable, CLI-facing identifier (``"madmom"``, ``"chroma-baseline"``).
    name: str
    #: Which analysis task this engine performs.
    kind: EngineKind

    def is_available(self) -> bool:
        """Whether this engine can run in the current environment."""
        ...

    def engine_info(self) -> EngineInfo:
        """Return identity and capability metadata for provenance."""
        ...


class ChordEngine(BaseEngine, Protocol):
    """An engine that estimates chords from audio."""

    def analyze(
        self,
        audio_path: Path,
        options: ChordAnalysisOptions,
    ) -> EngineResult:
        """Estimate chords for ``audio_path``."""
        ...


class LyricsEngine(BaseEngine, Protocol):
    """An engine that transcribes lyrics from audio."""

    def transcribe(
        self,
        audio_path: Path,
        options: LyricsOptions,
    ) -> EngineResult:
        """Transcribe lyrics for ``audio_path``."""
        ...


class BeatEngine(BaseEngine, Protocol):
    """An engine that detects beats and downbeats."""

    def detect_beats(self, audio_path: Path, options: dict[str, Any]) -> EngineResult:
        """Detect beats and downbeats for ``audio_path``."""
        ...


class KeyEngine(BaseEngine, Protocol):
    """An engine that estimates the musical key."""

    def detect_key(self, audio_path: Path, options: dict[str, Any]) -> EngineResult:
        """Estimate the key of ``audio_path``."""
        ...


class TempoEngine(BaseEngine, Protocol):
    """An engine that estimates tempo."""

    def detect_tempo(self, audio_path: Path, options: dict[str, Any]) -> EngineResult:
        """Estimate the tempo of ``audio_path``."""
        ...


class StemSeparationEngine(BaseEngine, Protocol):
    """An engine that separates a mix into stems."""

    def separate(
        self,
        audio_path: Path,
        options: StemSeparationOptions,
    ) -> EngineResult:
        """Separate ``audio_path`` into stems."""
        ...
