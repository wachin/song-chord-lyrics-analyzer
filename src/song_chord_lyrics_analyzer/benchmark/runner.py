"""Run a registered engine over benchmark cases (roadmap section 46).

`songlab benchmark --engine NAME` fills a case's hypothesis by actually running
the engine on the case's declared ``audio`` file instead of trusting a stored
one. The runner dispatches on the engine's kind: chord, key, tempo and lyrics
engines all produce output the section 44 metrics can score, and each fills its
own hypothesis fields. The run cost — processing time, peak RSS and the audio
window — comes from the engine's section 45 performance report, measured at run
time on this machine; the reference side is never touched (roadmap section 43),
and cases without ``audio`` keep their stored hypothesis untouched as well.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.benchmark.cases import BenchmarkCase
from song_chord_lyrics_analyzer.engines.base import (
    ChordAnalysisOptions,
    EngineKind,
    LyricsOptions,
)
from song_chord_lyrics_analyzer.metrics.adapters import (
    chord_labels,
    chord_segments,
    lyric_text,
    timed_words,
)
from song_chord_lyrics_analyzer.models.analysis import EngineResult
from song_chord_lyrics_analyzer.utils.errors import (
    AudioFileNotFoundError,
    DependencyError,
    InputError,
    SongLabError,
)

__all__ = ["EngineRun", "run_engine_on_cases"]

#: Kinds whose output a section 44 metric family can score.
_RUNNABLE_KINDS = (
    EngineKind.CHORDS,
    EngineKind.KEY,
    EngineKind.TEMPO,
    EngineKind.LYRICS,
)


@dataclass(frozen=True)
class EngineRun:
    """One engine invocation over one case, for the command's run summary."""

    song: str
    audio: Path
    kind: str
    summary: str
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


def _kind(engine: Any) -> EngineKind:
    """The engine's kind, refusing one the benchmark cannot score."""
    try:
        kind = EngineKind(engine.kind)
    except ValueError as error:
        raise InputError(
            f"Engine {engine.name!r} reports an unknown kind {engine.kind!r}.",
            hint="A benchmark engine must declare one of: chords, key, tempo, lyrics.",
        ) from error
    if kind not in _RUNNABLE_KINDS:
        scoreable = ", ".join(runnable.value for runnable in _RUNNABLE_KINDS)
        raise InputError(
            f"The benchmark cannot score a {kind.value!r} engine yet.",
            hint=f"Only these engine kinds have a metric family: {scoreable}.",
        )
    return kind


def _run(engine: Any, audio_path: Path, options: Any) -> EngineResult:
    """Call the engine method that matches its kind."""
    kind = _kind(engine)
    if kind is EngineKind.CHORDS:
        chord_options = options if isinstance(options, ChordAnalysisOptions) else None
        return engine.analyze(audio_path, chord_options or ChordAnalysisOptions())
    if kind is EngineKind.KEY:
        return engine.detect_key(audio_path, options if isinstance(options, dict) else {})
    if kind is EngineKind.TEMPO:
        return engine.detect_tempo(audio_path, options if isinstance(options, dict) else {})
    lyrics_options = options if isinstance(options, LyricsOptions) else None
    return engine.transcribe(audio_path, lyrics_options or LyricsOptions())


def _chord_hypothesis(result: EngineResult, audio_seconds: float | None) -> dict[str, Any]:
    """Chord fields, with timed segments through the section 44 adapter.

    A missing end is completed from the next chord's start — or from the
    measured audio duration for the last one — and an event the canonical model
    rejects aborts the run instead of being silently mangled.
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


def _hypothesis_for(
    engine: Any, result: EngineResult, audio_seconds: float | None
) -> tuple[dict[str, Any], str]:
    """The hypothesis fields and a one-line summary for the run note."""
    kind = _kind(engine)
    if kind is EngineKind.CHORDS:
        return _chord_hypothesis(result, audio_seconds), f"{len(result.chords)} chords"
    if kind is EngineKind.KEY:
        # An unresolved key survives as "unknown" so the family is scored as a
        # measured miss instead of quietly disappearing.
        label = result.key.label if result.key is not None else "unknown"
        return {"key": label}, f"key {label}"
    if kind is EngineKind.TEMPO:
        if result.tempo is None:
            return {}, "no tempo"
        bpm = float(result.tempo.bpm)
        return {"tempo_bpm": bpm}, f"{bpm:.1f} BPM"
    # LYRICS
    words = timed_words([word for segment in result.lyrics for word in segment.words])
    return (
        {
            "lyrics_text": lyric_text(result.lyrics),
            "lyrics_words": [{"text": text, "start": start} for text, start in words],
        },
        f"{len(result.lyrics)} lyric segments",
    )


def run_engine_on_cases(
    cases: Sequence[BenchmarkCase],
    engine: Any,
    *,
    options: Any | None = None,
) -> tuple[list[BenchmarkCase], list[EngineRun]]:
    """Run ``engine`` on every case that declares an ``audio`` path.

    Returns updated copies of the cases (the inputs are never mutated) plus
    one :class:`EngineRun` note per case that was actually processed.

    Raises:
        DependencyError: When the engine reports itself unavailable.
        InputError: When the engine's kind cannot be scored, when a declared
            audio file is missing, or when the engine fails or its output cannot
            be scored.
    """
    _kind(engine)  # refuse an unscoreable kind before doing any work
    if not engine.is_available():
        raise DependencyError(
            f"Engine {engine.name!r} is not available in this environment.",
            hint=(
                "Install the engine's optional dependencies, or pick another engine "
                "('songlab doctor' lists the registered ones)."
            ),
        )
    kind_value = EngineKind(engine.kind).value

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
            result = _run(engine, audio_path, options)
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

        fields, summary = _hypothesis_for(engine, result, audio_seconds)
        hypothesis = dict(case.hypothesis)
        hypothesis.update(fields)

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
                kind=kind_value,
                summary=summary,
                processing_time_seconds=updated_case.processing_time_seconds,
                peak_memory_bytes=updated_case.peak_memory_bytes,
                duration_seconds=updated_case.duration_seconds,
            )
        )
    return updated, runs
