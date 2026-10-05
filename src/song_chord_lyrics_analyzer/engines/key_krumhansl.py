"""Krumhansl-Schmuckler key detection engine (roadmap sections 31, 32 and 44).

The first key engine. It is deliberately simple and fully inspectable:

1. decode the audio to mono 22.05 kHz (librosa);
2. average a per-frame CQT chromagram into one pitch-class profile;
3. correlate that profile against the Krumhansl-Kessler major and minor
   profiles at all twelve rotations, and take the best;
4. report the winning tonic and mode with the correlation as confidence.

The correlation half is dependency-free library code (:func:`estimate_key`,
:func:`pearson_correlation`), so it is tested without numpy or librosa; the
optional DSP front end reports its availability honestly and raises
:class:`~song_chord_lyrics_analyzer.utils.errors.DependencyError` with an
install hint when missing. An empty (silent) profile yields an explicitly
unknown key rather than an invented one.
"""

from __future__ import annotations

import importlib
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.engines.base import EngineKind
from song_chord_lyrics_analyzer.models.analysis import EngineInfo, EngineResult
from song_chord_lyrics_analyzer.models.confidence import ConfidenceScore
from song_chord_lyrics_analyzer.models.music import PITCH_CLASS_NAMES, KeyEstimate, KeyMode
from song_chord_lyrics_analyzer.performance import PerformanceProbe
from song_chord_lyrics_analyzer.utils.errors import (
    AudioFileNotFoundError,
    DependencyError,
    InputError,
)

__all__ = [
    "ENGINE_NAME",
    "ENGINE_VERSION",
    "HOP_LENGTH",
    "MAJOR_PROFILE",
    "MINOR_PROFILE",
    "SAMPLE_RATE",
    "KeyCandidate",
    "KrumhanslKeyEngine",
    "estimate_key",
    "pearson_correlation",
]

#: Stable, CLI-facing engine identifier.
ENGINE_NAME = "krumhansl"
#: Engine version recorded as provenance in every result.
ENGINE_VERSION = "0.1.0"

#: Audio decoded to this mono sample rate before analysis.
SAMPLE_RATE = 22_050
#: Chroma frame hop in samples (~93 ms).
HOP_LENGTH = 2_048

#: Krumhansl-Kessler major and minor key profiles (C-rooted).
MAJOR_PROFILE: tuple[float, ...] = (
    6.35,
    2.23,
    3.48,
    2.33,
    4.38,
    4.09,
    2.52,
    5.19,
    2.39,
    3.66,
    2.29,
    2.88,
)
MINOR_PROFILE: tuple[float, ...] = (
    6.33,
    2.68,
    3.52,
    5.38,
    2.60,
    3.53,
    2.54,
    4.75,
    3.98,
    2.69,
    3.34,
    3.17,
)

_PROFILES: tuple[tuple[KeyMode, tuple[float, ...]], ...] = (
    (KeyMode.MAJOR, MAJOR_PROFILE),
    (KeyMode.MINOR, MINOR_PROFILE),
)


@dataclass(frozen=True)
class KeyCandidate:
    """The best key found for a pitch-class profile.

    Attributes:
        tonic: Root pitch-class name (sharps, e.g. ``"D#"``).
        mode: Major or minor.
        correlation: Pearson correlation of the profile with the winning
            rotated key profile, in ``[-1.0, 1.0]``.
    """

    tonic: str
    mode: KeyMode
    correlation: float


def pearson_correlation(left: Sequence[float], right: Sequence[float]) -> float:
    """Pearson correlation of two equal-length sequences.

    Returns ``0.0`` when either side has zero variance (a flat profile carries
    no key information), so callers never divide by zero.
    """
    if len(left) != len(right):
        raise ValueError(f"expected equal lengths, got {len(left)} and {len(right)}")
    count = len(left)
    if count == 0:
        return 0.0
    left_mean = sum(left) / count
    right_mean = sum(right) / count
    covariance = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True))
    left_variance = sum((a - left_mean) ** 2 for a in left)
    right_variance = sum((b - right_mean) ** 2 for b in right)
    denominator = math.sqrt(left_variance * right_variance)
    if denominator == 0.0:
        return 0.0
    return covariance / denominator


def estimate_key(profile: Sequence[float]) -> KeyCandidate | None:
    """The best Krumhansl-Schmuckler key for a 12-value pitch-class profile.

    Every rotation of the major and minor profiles is correlated against the
    profile; the highest correlation wins. ``None`` is returned when the
    profile carries no energy, so silence is reported as an unknown key instead
    of the best of a meaningless set.
    """
    if len(profile) != 12:
        raise ValueError(f"a pitch-class profile must have 12 values, got {len(profile)}")
    if sum(float(value) for value in profile) <= 0.0:
        return None
    best: KeyCandidate | None = None
    for shift in range(12):
        for mode, key_profile in _PROFILES:
            rotated = [key_profile[(index - shift) % 12] for index in range(12)]
            correlation = pearson_correlation(profile, rotated)
            if best is None or correlation > best.correlation:
                best = KeyCandidate(
                    tonic=PITCH_CLASS_NAMES[shift], mode=mode, correlation=correlation
                )
    return best


def _import_front_end() -> tuple[Any, Any]:
    """Import the optional DSP stack, or raise ``ImportError``."""
    librosa = importlib.import_module("librosa")
    numpy = importlib.import_module("numpy")
    return librosa, numpy


class KrumhanslKeyEngine:
    """Key detection by Krumhansl-Schmuckler correlation of a chroma profile."""

    name = ENGINE_NAME
    kind = EngineKind.KEY

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
                "Average CQT chroma profile correlated against the 24 rotated "
                "Krumhansl-Kessler major/minor key profiles."
            ),
            license="GPL-3.0-or-later",
            capabilities={"device": "cpu", "profiles": "krumhansl-kessler"},
        )

    def detect_key(self, audio_path: Path, options: dict[str, Any]) -> EngineResult:
        """Estimate the key of ``audio_path``.

        Raises:
            AudioFileNotFoundError: When the audio file does not exist.
            DependencyError: When numpy/librosa are not installed.
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

            chroma = librosa.feature.chroma_cqt(
                y=numpy.asarray(samples),
                sr=int(sample_rate),
                hop_length=HOP_LENGTH,
            )
            profile = [float(value) for value in chroma.mean(axis=1)]
        finally:
            report = probe.stop()

        candidate = estimate_key(profile)
        if candidate is None:
            key = KeyEstimate(mode=KeyMode.UNKNOWN, confidence=ConfidenceScore.unknown(self.name))
        else:
            confidence = ConfidenceScore.from_value(
                max(0.0, min(1.0, candidate.correlation)), source=self.name
            )
            key = KeyEstimate(
                tonic=candidate.tonic,
                mode=candidate.mode,
                confidence=confidence,
                source=self.name,
            )

        return EngineResult(
            engine=self.name,
            kind=self.kind.value,
            engine_version=ENGINE_VERSION,
            audio_path=audio_path,
            key=key,
            processing_time_seconds=report.processing_time_seconds,
            raw={"pitch_class_profile": profile},
            metadata={
                "performance": report.as_dict(),
                "correlation": candidate.correlation if candidate is not None else None,
                "sample_rate": SAMPLE_RATE,
                "hop_length": HOP_LENGTH,
            },
        )
