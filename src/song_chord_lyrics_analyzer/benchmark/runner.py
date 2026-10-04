"""Run a registered engine over benchmark cases (roadmap section 46).

`songlab benchmark --engine NAME` fills a case's hypothesis by actually
running the engine on the case's declared ``audio`` file instead of trusting a
stored one. The run cost — processing time, peak RSS and the audio window —
comes from the engine's section 45 performance report, measured at run time on
this machine; the reference side is never touched (roadmap section 43), and
cases without ``audio`` keep their stored hypothesis untouched as well.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.benchmark.cases import BenchmarkCase
from song_chord_lyrics_analyzer.engines.base import ChordAnalysisOptions, ChordEngine
from song_chord_lyrics_analyzer.metrics.adapters import chord_labels, chord_segments
from song_chord_lyrics_analyzer.models.analysis import EngineResult
from song_chord_lyrics_analyzer.utils.errors import (
    AudioFileNotFoundError,
    DependencyError,
    InputError,
    SongLabError,
)

__all__ = ["EngineRun", "run_engine_on_cases"]


@dataclass(frozen=True)
class EngineRun:
    """One engine invocation over one case, for the command's run summary."""

    song: str
    audio: Path
    chord_count: int
    processing_time_seconds: float | None
    peak_memory_bytes: int | None
    duration_seconds: float | None


def _number(value: Any) -> float | None:
    """A real finite positive float from engine metadata, or ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number <= 0.0:  # NaN or nonsense
        return None
    return number


def _hypothesis_from(result: EngineResult, audio_seconds: float | None) -> dict[str, Any]:
    """The scored hypothesis fields derived from one engine result.

    Timed segments go through the section 44 adapter, so a missing end is
    completed from the next chord's start — or from the measured audio
    duration for the last one — and an event the canonical model rejects
    aborts the run instead of being silently mangled.
    """
    try:
        segments = chord_segments(result.chords, end=audio_seconds)
    except ValueError as error:
        raise InputError(
            f"Engine {result.engine!r} produced chords the canonical model rejects: {error}",
            hint="Chord events need ordered, non-overlapping intervals with a known end.",
        ) from error
    return {
        "chords": [{"start": start, "end": end, "label": label} for start, end, label in segments],
        "chord_labels": chord_labels(result.chords),
    }


def run_engine_on_cases(
    cases: Sequence[BenchmarkCase],
    engine: ChordEngine,
    *,
    options: ChordAnalysisOptions | None = None,
) -> tuple[list[BenchmarkCase], list[EngineRun]]:
    """Run ``engine`` on every case that declares an ``audio`` path.

    Returns updated copies of the cases (the inputs are never mutated) plus
    one :class:`EngineRun` note per case that was actually processed.

    Raises:
        DependencyError: When the engine reports itself unavailable.
        AudioFileNotFoundError: When a declared audio file is missing.
        InputError: When the engine fails or its output cannot be scored.
    """
    if not engine.is_available():
        raise DependencyError(
            f"Engine {engine.name!r} is not available in this environment.",
            hint=(
                "Install the engine's optional dependencies, or pick another engine "
                "('songlab doctor' lists the registered ones)."
            ),
        )
    run_options = options if options is not None else ChordAnalysisOptions()

    updated: list[BenchmarkCase] = []
    runs: list[EngineRun] = []
    for case in cases:
        audio_path = case.audio_path()
        if audio_path is None:
            updated.append(case)
            continue
        if not audio_path.exists():
            raise AudioFileNotFoundError(audio_path)
        try:
            result = engine.analyze(audio_path, run_options)
        except SongLabError:
            raise
        except Exception as error:  # engine bugs become a user-facing error
            raise InputError(
                f"Engine {engine.name!r} failed on case {case.song!r}: {error}",
                hint="Check the audio file and the engine's requirements, then retry.",
            ) from error

        performance = result.metadata.get("performance")
        if not isinstance(performance, dict):
            performance = {}
        audio_seconds = _number(performance.get("audio_seconds"))
        processing = _number(result.processing_time_seconds)
        peak_memory_value = performance.get("peak_rss_bytes")
        peak_memory = peak_memory_value if isinstance(peak_memory_value, int) else None

        hypothesis = dict(case.hypothesis)
        hypothesis.update(_hypothesis_from(result, audio_seconds))

        updated_case = replace(
            case,
            hypothesis=hypothesis,
            engine=result.engine,
            engine_version=result.engine_version,
            duration_seconds=(
                case.duration_seconds if case.duration_seconds is not None else audio_seconds
            ),
            processing_time_seconds=(
                processing if processing is not None else case.processing_time_seconds
            ),
            peak_memory_bytes=(peak_memory if peak_memory is not None else case.peak_memory_bytes),
        )
        updated.append(updated_case)
        runs.append(
            EngineRun(
                song=case.song,
                audio=audio_path,
                chord_count=len(result.chords),
                processing_time_seconds=updated_case.processing_time_seconds,
                peak_memory_bytes=updated_case.peak_memory_bytes,
                duration_seconds=updated_case.duration_seconds,
            )
        )
    return updated, runs
