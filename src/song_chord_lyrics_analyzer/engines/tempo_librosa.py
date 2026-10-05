"""librosa tempo estimation engine (roadmap sections 33 and 44).

The first tempo engine. It is deliberately simple and fully inspectable:

1. decode the audio to mono 22.05 kHz (librosa);
2. run librosa's beat tracker and read the tempo it reports;
3. record the half-time and double-time readings as *alternatives*.

Step 3 matters more than it looks. A beat tracker cannot tell whether it heard
the beat or the half beat, so the estimate is kept as read and the competing
readings travel with it instead of being folded into a single number (roadmap
section 33 and the tempo-estimation convention in ``docs/BENCHMARK.md``); the
section 44 metrics then report the absolute, half-time and double-time errors
side by side. The engine reports **no** confidence: librosa does not produce a
calibrated one, and inventing a number would be exactly the kind of invented
confidence this project refuses.

The DSP front end (numpy + librosa) is **optional**: :meth:`LibrosaTempoEngine.is_available`
reports whether it is importable, and :meth:`LibrosaTempoEngine.detect_tempo`
raises :class:`~song_chord_lyrics_analyzer.utils.errors.DependencyError` with an
install hint instead of failing obscurely. Beat *positions* are a separate
engine (roadmap section 34); this one only reports tempo.
"""

from __future__ import annotations

import importlib
import math
import time
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.engines.base import EngineKind
from song_chord_lyrics_analyzer.models.analysis import EngineInfo, EngineResult
from song_chord_lyrics_analyzer.models.confidence import ConfidenceScore
from song_chord_lyrics_analyzer.models.music import TempoEstimate
from song_chord_lyrics_analyzer.performance import PerformanceProbe
from song_chord_lyrics_analyzer.utils.errors import (
    AudioFileNotFoundError,
    DependencyError,
    InputError,
)

__all__ = [
    "ENGINE_NAME",
    "ENGINE_VERSION",
    "SAMPLE_RATE",
    "LibrosaTempoEngine",
    "metrical_alternatives",
]

#: Stable, CLI-facing engine identifier.
ENGINE_NAME = "librosa-tempo"
#: Engine version recorded as provenance in every result.
ENGINE_VERSION = "0.1.0"

#: Audio decoded to this mono sample rate before analysis.
SAMPLE_RATE = 22_050


def metrical_alternatives(bpm: float) -> list[float]:
    """The half-time and double-time readings of ``bpm``.

    Returned as :attr:`~song_chord_lyrics_analyzer.models.music.TempoEstimate.alternatives`
    so the ambiguity is preserved instead of resolved: which of the three is
    musically correct depends on the metrical context, which a tempo engine
    does not see. No plausibility window is applied here — the caller (and the
    section 44 metrics) decide what to do with them.
    """
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError(f"bpm must be a positive finite value, got {bpm!r}")
    return [bpm / 2.0, bpm * 2.0]


def _import_front_end() -> tuple[Any, Any]:
    """Import the optional DSP stack, or raise ``ImportError``."""
    librosa = importlib.import_module("librosa")
    numpy = importlib.import_module("numpy")
    return librosa, numpy


class LibrosaTempoEngine:
    """Tempo estimation with librosa's beat tracker."""

    name = ENGINE_NAME
    kind = EngineKind.TEMPO

    def is_available(self) -> bool:
        """Whether numpy and librosa can be imported right now."""
        try:
            _import_front_end()
        except ImportError:
            return False
        return True

    def engine_info(self) -> EngineInfo:
        """Identity and capability metadata recorded as provenance."""
        return EngineInfo(
            name=self.name,
            kind=self.kind.value,
            version=ENGINE_VERSION,
            available=self.is_available(),
            description=(
                "librosa beat_track tempo at 22.05 kHz, with the half-time and "
                "double-time readings kept as reported alternatives."
            ),
            license="GPL-3.0-or-later",
            capabilities={
                "device": "cpu",
                "half_double_alternatives": True,
                "confidence": False,
            },
        )

    def detect_tempo(self, audio_path: Path, options: dict[str, Any]) -> EngineResult:
        """Estimate the tempo of ``audio_path``.

        Raises:
            AudioFileNotFoundError: When the audio file does not exist.
            DependencyError: When numpy/librosa are not installed.
            InputError: When the beat tracker reports no usable tempo.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise AudioFileNotFoundError(audio_path)

        startup_started = time.perf_counter()
        try:
            librosa, numpy = _import_front_end()
        except ImportError as error:
            raise DependencyError(
                f"Engine {self.name!r} needs numpy and librosa, which are not installed.",
                hint="Install the optional DSP stack: pip install numpy librosa",
            ) from error
        startup_seconds = time.perf_counter() - startup_started

        probe = PerformanceProbe(startup_time_seconds=startup_seconds, device="cpu")
        probe.start()
        try:
            samples, sample_rate = librosa.load(str(audio_path), sr=SAMPLE_RATE, mono=True)
            audio_seconds = float(len(samples)) / float(sample_rate)
            if audio_seconds <= 0.0:
                raise InputError(
                    f"Engine {self.name!r} decoded no audio from {audio_path.name!r}.",
                    hint="Check that the file contains a decodable audio stream.",
                )
            probe.audio_seconds = audio_seconds

            reported, _frames = librosa.beat.beat_track(y=samples, sr=int(sample_rate))
            bpm = float(numpy.atleast_1d(reported)[0])
        finally:
            report = probe.stop()

        if not math.isfinite(bpm) or bpm <= 0.0:
            raise InputError(
                f"Engine {self.name!r} found no usable tempo in {audio_path.name!r}.",
                hint="The audio may be silent or too short to track a beat.",
            )
        alternatives = metrical_alternatives(bpm)

        return EngineResult(
            engine=self.name,
            kind=self.kind.value,
            engine_version=ENGINE_VERSION,
            audio_path=audio_path,
            tempo=TempoEstimate(
                bpm=bpm,
                confidence=ConfidenceScore.unknown(self.name),
                source=self.name,
                alternatives=alternatives,
            ),
            processing_time_seconds=report.processing_time_seconds,
            metadata={
                "performance": report.as_dict(),
                "sample_rate": SAMPLE_RATE,
                "alternatives_bpm": alternatives,
            },
        )
