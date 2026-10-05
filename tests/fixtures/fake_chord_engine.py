"""A deterministic fake chord engine for benchmark and CLI tests.

Behaves like a real engine where it matters for the benchmark: it reports
availability, produces canonical chord events (optionally with a missing
final end, like engines that do not know the track length) and measures its
run through a section 45-style performance block in ``metadata``. The audio
file is never touched.
"""

from __future__ import annotations

from pathlib import Path

from song_chord_lyrics_analyzer.engines.base import ChordAnalysisOptions, EngineKind
from song_chord_lyrics_analyzer.models.analysis import EngineInfo, EngineResult
from song_chord_lyrics_analyzer.models.music import ChordEvent, ChordQuality

__all__ = ["FakeChordEngine"]


class FakeChordEngine:
    """A ``ChordEngine`` that returns canned events without reading the audio."""

    name = "fake-chords"
    kind = EngineKind.CHORDS

    def __init__(
        self,
        *,
        available: bool = True,
        chords: list[ChordEvent] | None = None,
        processing_time_seconds: float = 2.5,
        audio_seconds: float | None = 4.0,
        peak_rss_bytes: int | None = 4_242_424,
        failure: Exception | None = None,
        version: str = "9.9.0",
    ) -> None:
        self.available = available
        self.processing_time_seconds = processing_time_seconds
        self.audio_seconds = audio_seconds
        self.peak_rss_bytes = peak_rss_bytes
        self.failure = failure
        self.version = version
        self.calls: list[Path] = []
        self.options_seen: list[ChordAnalysisOptions] = []
        if chords is None:
            chords = [
                ChordEvent(
                    start=0.0,
                    end=2.0,
                    root="C",
                    quality=ChordQuality.MAJOR,
                    source=self.name,
                ),
                ChordEvent(
                    start=2.0,
                    end=4.0,
                    root="G",
                    quality=ChordQuality.MAJOR,
                    source=self.name,
                ),
            ]
        self.chords = chords

    def is_available(self) -> bool:
        return self.available

    def engine_info(self) -> EngineInfo:
        return EngineInfo(name=self.name, kind=self.kind.value, version=self.version)

    def analyze(self, audio_path: Path, options: ChordAnalysisOptions) -> EngineResult:
        self.calls.append(Path(audio_path))
        self.options_seen.append(options)
        if self.failure is not None:
            raise self.failure
        return EngineResult(
            engine=self.name,
            kind=self.kind.value,
            engine_version=self.version,
            audio_path=Path(audio_path),
            chords=list(self.chords),
            processing_time_seconds=self.processing_time_seconds,
            metadata={
                "performance": {
                    "processing_time_seconds": self.processing_time_seconds,
                    "audio_seconds": self.audio_seconds,
                    "peak_rss_bytes": self.peak_rss_bytes,
                }
            },
        )
