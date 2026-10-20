"""Analysis containers, engine results and provenance (roadmap sections 39-41, 61-62).

The canonical document is independent from Markdown and ChordPro, and every
derived value can be traced back to the engine, model and configuration that
produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.models.audio import AudioDocument
from song_chord_lyrics_analyzer.models.confidence import ConfidenceScore
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment
from song_chord_lyrics_analyzer.models.music import (
    BarEvent,
    BeatEvent,
    ChordEvent,
    DownbeatEvent,
    KeyEstimate,
    NoteEvent,
    Stem,
    TempoEstimate,
)

__all__ = [
    "AlignmentResult",
    "AnalysisResult",
    "AnalysisRun",
    "EngineInfo",
    "EngineResult",
    "Provenance",
    "RunStatus",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus(str, Enum):
    """Lifecycle state of an analysis run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class EngineInfo:
    """Identity and capabilities of an engine (used for provenance)."""

    name: str
    kind: str
    version: str | None = None
    available: bool | None = None
    description: str | None = None
    license: str | None = None
    model: str | None = None
    model_version: str | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineResult:
    """Raw and canonical output of one engine invocation (roadmap section 7).

    ``raw`` preserves the untouched engine payload so that normalization can
    always be re-run and disagreements remain inspectable.
    """

    engine: str
    kind: str
    engine_version: str | None = None
    audio_path: Path | None = None
    chords: list[ChordEvent] = field(default_factory=list)
    lyrics: list[LyricSegment] = field(default_factory=list)
    beats: list[BeatEvent] = field(default_factory=list)
    downbeats: list[DownbeatEvent] = field(default_factory=list)
    bars: list[BarEvent] = field(default_factory=list)
    key: KeyEstimate | None = None
    tempo: TempoEstimate | None = None
    notes: list[NoteEvent] = field(default_factory=list)
    stems: list[Stem] = field(default_factory=list)
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore.unknown)
    processing_time_seconds: float | None = None
    raw: Any | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.audio_path is not None:
            self.audio_path = Path(self.audio_path)

    @property
    def is_empty(self) -> bool:
        """Whether the engine produced no usable output at all."""
        return not any(
            (
                self.chords,
                self.lyrics,
                self.beats,
                self.downbeats,
                self.bars,
                self.notes,
                self.stems,
                self.key,
                self.tempo,
            )
        )


@dataclass
class AlignmentResult:
    """Alignment of lyrics, chords and the rhythmic grid on one timeline.

    The canonical timeline permits overlapping semantic events: a word may span
    a chord change and a lyric line may contain several chords (roadmap
    sections 36 and 37).
    """

    lyrics: list[LyricSegment] = field(default_factory=list)
    chords: list[ChordEvent] = field(default_factory=list)
    beats: list[BeatEvent] = field(default_factory=list)
    downbeats: list[DownbeatEvent] = field(default_factory=list)
    bars: list[BarEvent] = field(default_factory=list)
    method: str | None = None
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore.unknown)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Provenance:
    """Reproducibility record for one analysis (roadmap sections 61 and 62)."""

    application_version: str
    input_path: str | None = None
    input_hash: str | None = None
    python_version: str | None = None
    platform: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    engines: dict[str, EngineInfo] = field(default_factory=dict)
    configuration: dict[str, Any] = field(default_factory=dict)
    preprocessing: list[str] = field(default_factory=list)
    normalization: list[str] = field(default_factory=list)
    fusion_rules: list[str] = field(default_factory=list)
    cache_hit: bool | None = None


@dataclass
class AnalysisRun:
    """Bookkeeping for one end-to-end analysis execution."""

    status: RunStatus = RunStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock duration of the run when it finished."""
        if self.started_at is None or self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()


@dataclass
class AnalysisResult:
    """The canonical analysis document.

    Raw engine outputs live in :attr:`raw`; normalized and user-corrected
    layers are added by later pipeline stages and never overwrite this
    structure (roadmap sections 38, 73).
    """

    provenance: Provenance
    audio: AudioDocument | None = None
    lyrics: list[LyricSegment] = field(default_factory=list)
    chords: list[ChordEvent] = field(default_factory=list)
    beats: list[BeatEvent] = field(default_factory=list)
    downbeats: list[DownbeatEvent] = field(default_factory=list)
    bars: list[BarEvent] = field(default_factory=list)
    key: KeyEstimate | None = None
    tempo: TempoEstimate | None = None
    notes: list[NoteEvent] = field(default_factory=list)
    stems: list[Stem] = field(default_factory=list)
    alignment: AlignmentResult | None = None
    engines: dict[str, EngineInfo] = field(default_factory=dict)
    run: AnalysisRun = field(default_factory=AnalysisRun)
    raw: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_chords(self) -> bool:
        """Whether any chord (including ``N``) was detected."""
        return bool(self.chords)

    @property
    def has_lyrics(self) -> bool:
        """Whether any lyric segment was detected."""
        return bool(self.lyrics)
