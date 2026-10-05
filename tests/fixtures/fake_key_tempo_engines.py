"""Deterministic fake key, tempo and lyrics engines for benchmark tests.

They mirror :class:`~tests.fixtures.fake_chord_engine.FakeChordEngine`: report
availability, return a canned canonical result (optionally with an unresolved
key) and measure their run through a section 45-style performance block. The
audio file is never touched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.engines.base import EngineKind
from song_chord_lyrics_analyzer.models.analysis import EngineInfo, EngineResult
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricWord
from song_chord_lyrics_analyzer.models.music import KeyEstimate, KeyMode, TempoEstimate

__all__ = ["FakeKeyEngine", "FakeLyricsEngine", "FakeTempoEngine"]


def _performance(processing: float, audio_seconds: float | None) -> dict[str, Any]:
    return {
        "processing_time_seconds": processing,
        "audio_seconds": audio_seconds,
        "peak_rss_bytes": 1_048_576,
    }


class FakeKeyEngine:
    """A ``KeyEngine`` returning a canned key without reading the audio."""

    name = "fake-key"
    kind = EngineKind.KEY

    def __init__(
        self,
        *,
        available: bool = True,
        tonic: str | None = "C",
        mode: KeyMode = KeyMode.MAJOR,
        version: str = "1.0.0",
    ) -> None:
        self.available = available
        self.tonic = tonic
        self.mode = mode
        self.version = version
        self.calls: list[Path] = []

    def is_available(self) -> bool:
        return self.available

    def engine_info(self) -> EngineInfo:
        return EngineInfo(name=self.name, kind=self.kind.value, version=self.version)

    def detect_key(self, audio_path: Path, options: dict[str, Any]) -> EngineResult:
        self.calls.append(Path(audio_path))
        return EngineResult(
            engine=self.name,
            kind=self.kind.value,
            engine_version=self.version,
            audio_path=Path(audio_path),
            key=KeyEstimate(tonic=self.tonic, mode=self.mode, source=self.name),
            processing_time_seconds=1.5,
            metadata={"performance": _performance(1.5, 30.0)},
        )


class FakeTempoEngine:
    """A ``TempoEngine`` returning a canned BPM without reading the audio."""

    name = "fake-tempo"
    kind = EngineKind.TEMPO

    def __init__(
        self,
        *,
        available: bool = True,
        bpm: float = 120.0,
        version: str = "1.0.0",
    ) -> None:
        self.available = available
        self.bpm = bpm
        self.version = version
        self.calls: list[Path] = []

    def is_available(self) -> bool:
        return self.available

    def engine_info(self) -> EngineInfo:
        return EngineInfo(name=self.name, kind=self.kind.value, version=self.version)

    def detect_tempo(self, audio_path: Path, options: dict[str, Any]) -> EngineResult:
        self.calls.append(Path(audio_path))
        return EngineResult(
            engine=self.name,
            kind=self.kind.value,
            engine_version=self.version,
            audio_path=Path(audio_path),
            tempo=TempoEstimate(bpm=self.bpm, source=self.name),
            processing_time_seconds=0.5,
            metadata={"performance": _performance(0.5, 30.0)},
        )


class FakeLyricsEngine:
    """A ``LyricsEngine`` returning canned lyric segments without reading audio."""

    name = "fake-lyrics"
    kind = EngineKind.LYRICS

    def __init__(self, *, available: bool = True, version: str = "1.0.0") -> None:
        self.available = available
        self.version = version
        self.calls: list[Path] = []

    def is_available(self) -> bool:
        return self.available

    def engine_info(self) -> EngineInfo:
        return EngineInfo(name=self.name, kind=self.kind.value, version=self.version)

    def transcribe(self, audio_path: Path, options: Any) -> EngineResult:
        self.calls.append(Path(audio_path))
        return EngineResult(
            engine=self.name,
            kind=self.kind.value,
            engine_version=self.version,
            audio_path=Path(audio_path),
            lyrics=[
                LyricSegment(
                    text="hola mundo",
                    words=[LyricWord(text="hola", start=0.5), LyricWord(text="mundo", start=1.5)],
                    source=self.name,
                )
            ],
            processing_time_seconds=2.0,
            metadata={"performance": _performance(2.0, 30.0)},
        )
