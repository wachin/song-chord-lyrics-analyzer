"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from fixtures.audio import write_sine_wav, write_wav_bytes
from song_chord_lyrics_analyzer.engines.base import EngineKind
from song_chord_lyrics_analyzer.models.analysis import EngineInfo, EngineResult


@pytest.fixture
def make_wav() -> Callable[..., Path]:
    """Return a factory that writes small synthetic WAV files."""

    def _factory(path: Path, **kwargs: object) -> Path:
        return write_sine_wav(path, **kwargs)  # type: ignore[arg-type]

    return _factory


@pytest.fixture
def tone_wav(tmp_path: Path) -> Path:
    """A one second, 44.1 kHz stereo sine tone."""
    return write_sine_wav(tmp_path / "tone.wav", seconds=1.0)


@pytest.fixture
def corrupt_wav(tmp_path: Path) -> Path:
    """A file with a ``.wav`` extension that is not a WAV stream."""
    return write_wav_bytes(tmp_path / "corrupt.wav")


class FakeEngine:
    """Minimal engine satisfying the registry contract."""

    def __init__(
        self,
        name: str,
        kind: EngineKind = EngineKind.CHORDS,
        *,
        available: bool = True,
        version: str = "0.0.0",
    ) -> None:
        self.name = name
        self.kind = kind
        self._available = available
        self._version = version

    def is_available(self) -> bool:
        return self._available

    def engine_info(self) -> EngineInfo:
        return EngineInfo(
            name=self.name,
            kind=self.kind.value,
            version=self._version,
            available=self._available,
        )

    def analyze(self, audio_path: Path, options: object = None) -> EngineResult:
        return EngineResult(engine=self.name, kind=self.kind.value, audio_path=audio_path)

    def transcribe(self, audio_path: Path, options: object = None) -> EngineResult:
        return EngineResult(engine=self.name, kind=self.kind.value, audio_path=audio_path)


@pytest.fixture
def fake_engine() -> type[FakeEngine]:
    """Return the :class:`FakeEngine` class so tests can build engines."""
    return FakeEngine
