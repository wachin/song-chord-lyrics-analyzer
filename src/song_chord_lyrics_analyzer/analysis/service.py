"""Run the registered engines and assemble one canonical document.

Roadmap sections 8, 9, 61 and 62: an analysis is the canonical
:class:`~song_chord_lyrics_analyzer.models.analysis.AnalysisResult` plus the
:class:`~song_chord_lyrics_analyzer.models.analysis.Provenance` record that says
where every value came from. This service owns that assembly and nothing else -
no argument parsing, no formatting.

Three rules shape it:

* **A failing engine never destroys a document.** Chords, lyrics, key and tempo
  are independent; if one fails the others are still kept, the failure becomes a
  warning, and the run is marked ``partial``. Only when *nothing* could run does
  the analysis fail. This is what makes the lyrics engine, whose model is a
  ~640 MB download, safe to register: an environment without it still gets a
  full chord/key/tempo document plus a ``skipped`` lyrics step that says so.
* **An unavailable engine is never called.** Availability is checked first, so
  a missing optional dependency is reported as a skipped step instead of an
  exception mid-run.
* **Nothing is invented.** Confidence the engines did not report stays absent,
  and a step that produced nothing contributes no field.

Timing comes from each engine's own section 45 measurement, never from a second
probe around it.
"""

from __future__ import annotations

import platform
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer import __version__
from song_chord_lyrics_analyzer.alignment import parse_timed_text
from song_chord_lyrics_analyzer.analysis.chunking import (
    DEFAULT_CHORD_CHUNK_SECONDS,
    analyze_chords_in_windows,
)
from song_chord_lyrics_analyzer.analysis.progress import ProgressEvent
from song_chord_lyrics_analyzer.audio.probe import compute_file_hash, probe_audio
from song_chord_lyrics_analyzer.engines.base import (
    ChordAnalysisOptions,
    EngineKind,
    LyricsOptions,
)
from song_chord_lyrics_analyzer.engines.registry import create_default_registry
from song_chord_lyrics_analyzer.models.analysis import (
    AnalysisResult,
    AnalysisRun,
    EngineResult,
    Provenance,
    RunStatus,
)
from song_chord_lyrics_analyzer.utils.errors import DependencyError, InputError, SongLabError
from song_chord_lyrics_analyzer.utils.logging import get_logger
from song_chord_lyrics_analyzer.utils.text import pluralize

__all__ = [
    "DEFAULT_CHORD_CHUNK_SECONDS",
    "SUPPORTED_KINDS",
    "AnalysisOutcome",
    "ProgressEvent",
    "StepOutcome",
    "StepStatus",
    "run_analysis",
    "validate_windowing_options",
    "with_lyrics_from_timed_text",
]

_logger = get_logger("analysis")

#: Engine kinds this service runs today: chords, lyrics, key and tempo. Each
#: one is independent, so a lyrics engine that is not installed yet costs a
#: documented *skipped* step and never the rest of the document.
SUPPORTED_KINDS: tuple[EngineKind, ...] = (
    EngineKind.CHORDS,
    EngineKind.LYRICS,
    EngineKind.KEY,
    EngineKind.TEMPO,
)


class StepStatus(str, Enum):
    """Outcome of one engine step inside an analysis."""

    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class StepOutcome:
    """One engine step of an analysis, for the command's run summary."""

    kind: str
    engine: str
    status: StepStatus
    detail: str | None = None
    processing_time_seconds: float | None = None


@dataclass(frozen=True)
class AnalysisOutcome:
    """The assembled document plus the per-step run summary."""

    result: AnalysisResult
    steps: tuple[StepOutcome, ...]

    @property
    def total_processing_seconds(self) -> float | None:
        """Sum of the measured engine run times, or ``None`` when none ran."""
        times = [
            step.processing_time_seconds
            for step in self.steps
            if step.processing_time_seconds is not None
        ]
        return sum(times) if times else None


def _resolve(registry: Any, kind: EngineKind, name: str | None) -> Any | None:
    """The engine to use for ``kind``: an explicit name, else the first
    available one, else the first registered (so its own error explains why)."""
    if name is not None:
        return registry.get(kind, name)
    available = registry.available(kind)
    if available:
        return registry.get(kind, available[0])
    registered = registry.names(kind)
    return registry.get(kind, registered[0]) if registered else None


def _call(engine: Any, kind: EngineKind, audio_path: Path) -> EngineResult:
    """Invoke the engine method that matches its kind."""
    if kind is EngineKind.CHORDS:
        return engine.analyze(audio_path, ChordAnalysisOptions())
    if kind is EngineKind.LYRICS:
        return engine.transcribe(audio_path, LyricsOptions())
    if kind is EngineKind.KEY:
        return engine.detect_key(audio_path, {})
    return engine.detect_tempo(audio_path, {})


def _describe(kind: EngineKind, result: EngineResult) -> str:
    """A one-line summary of what an engine produced."""
    if kind is EngineKind.CHORDS:
        windows = result.metadata.get("windows")
        windowed = f", {windows} windows" if isinstance(windows, int) else ""
        return f"{len(result.chords)} chords{windowed}"
    if kind is EngineKind.LYRICS:
        words = sum(len(segment.words) for segment in result.lyrics)
        if not result.lyrics:
            return "no lyrics"
        return f"{pluralize(len(result.lyrics), 'lyric segment')}, {pluralize(words, 'word')}"
    if kind is EngineKind.KEY:
        return f"key {result.key.label}" if result.key is not None else "no key"
    if result.tempo is None:
        return "no tempo"
    return f"{result.tempo.bpm:.1f} BPM"


def _merge(target: AnalysisResult, kind: EngineKind, result: EngineResult) -> None:
    """Copy one engine's canonical output into the document."""
    if kind is EngineKind.CHORDS:
        target.chords = list(result.chords)
    elif kind is EngineKind.LYRICS:
        target.lyrics = list(result.lyrics)
    elif kind is EngineKind.KEY:
        target.key = result.key
    else:
        target.tempo = result.tempo
    if result.raw is not None:
        target.raw[result.engine] = result.raw


def _notify(callback: Callable[[ProgressEvent], None] | None, event: ProgressEvent) -> None:
    """Report one progress event; a missing callback is a no-op, never a guess."""
    if callback is not None:
        callback(event)


def _window_reporter(
    kind: EngineKind,
    engine_name: str,
    on_progress: Callable[[ProgressEvent], None] | None,
) -> Callable[[int, int, Any], None] | None:
    """A per-window progress reporter, or ``None`` when nobody is listening."""
    if on_progress is None:
        return None

    def report(index: int, total: int, _chunk: Any) -> None:
        on_progress(
            ProgressEvent(kind.value, engine_name, index, total, f"window {index} of {total}")
        )

    return report


def validate_windowing_options(
    chord_chunk_seconds: float | None, chord_overlap_seconds: float
) -> None:
    """Reject impossible windowing options before any engine is called.

    Public so a front end that decodes before it analyses - ``songlab play``
    opens the audio first - can report a typo in the flags without paying for
    the decode.

    Raises:
        InputError: When the window length is not positive, or when the overlap
            is negative or as long as the window itself.
    """
    if chord_chunk_seconds is None:
        if chord_overlap_seconds:
            raise InputError(
                "A chord overlap needs a window length to overlap within.",
                hint="Pass the window length too, for example --chord-chunk-seconds 120.",
            )
        return
    if chord_chunk_seconds <= 0.0:
        raise InputError(
            f"The chord window length must be positive, got {chord_chunk_seconds!r}",
            hint="Pass a window length in seconds, for example --chord-chunk-seconds 120.",
        )
    if chord_overlap_seconds < 0.0:
        raise InputError(
            f"The chord window overlap must not be negative, got {chord_overlap_seconds!r}"
        )
    if chord_overlap_seconds >= chord_chunk_seconds:
        raise InputError(
            "The chord window overlap must be smaller than the window length.",
            hint="An overlap as long as the window would never advance.",
        )


def _seconds_label(value: float) -> str:
    """A window length as provenance records it: ``120`` rather than ``120.0``."""
    return f"{value:g}"


def _status(steps: list[StepOutcome]) -> RunStatus:
    """``partial`` when some step did not deliver, ``failed`` when none did."""
    ok = [step for step in steps if step.status is StepStatus.OK]
    if ok and len(ok) == len(steps):
        return RunStatus.SUCCEEDED
    if ok:
        return RunStatus.PARTIAL
    return RunStatus.FAILED


def with_lyrics_from_timed_text(outcome: AnalysisOutcome, source: Path) -> AnalysisOutcome:
    """Layer ``result.lyrics`` from an external timed-text file over the run..

    The file wins over any engine-transcribed lyric layer: the user asked for
    these lyrics explicitly, and the alignment rules live in
    :mod:`song_chord_lyrics_analyzer.alignment`. The step summary and the
    provenance configuration record the file as the lyric source, so nothing
    in the document claims an engine provenance it does not have, and the run
    status is recomputed from the resulting steps. A read or parse error
    raises before anything is changed - the engine outcome stays intact.

    Raises:
        :class:`~song_chord_lyrics_analyzer.utils.errors.InputError`: The file
            cannot be read or parsed as ``.lrc``/``.srt``.
    """
    lines = parse_timed_text(source)
    detail = f"{pluralize(len(lines), 'lyric segment')} from {Path(source).name}"
    steps: list[StepOutcome] = []
    replaced = False
    for step in outcome.steps:
        if step.kind == "lyrics":
            steps.append(
                replace(
                    step,
                    engine="timed-text",
                    status=StepStatus.OK,
                    detail=detail,
                    processing_time_seconds=None,
                )
            )
            replaced = True
        else:
            steps.append(step)
    if not replaced:  # the lyrics layer never ran: the file is the step now
        steps.append(
            StepOutcome(
                "lyrics",
                "timed-text",
                StepStatus.OK,
                detail,
                processing_time_seconds=None,
            )
        )
    document = replace(
        outcome.result,
        lyrics=list(lines),
        warnings=list(outcome.result.warnings),
    )
    configuration = dict(document.provenance.configuration)
    configuration["lyrics_from"] = str(source)
    provenance = replace(document.provenance, configuration=configuration)
    document = replace(document, provenance=provenance)
    document = replace(document, run=replace(document.run, status=_status(steps)))
    return AnalysisOutcome(result=document, steps=tuple(steps))


def run_analysis(
    audio_path: Path,
    *,
    registry: Any | None = None,
    engines: Mapping[str, str] | None = None,
    input_hash: bool = True,
    chord_chunk_seconds: float | None = None,
    chord_overlap_seconds: float = 0.0,
    on_progress: Callable[[ProgressEvent], None] | None = None,
) -> AnalysisOutcome:
    """Analyse ``audio_path`` and return the canonical document.

    Args:
        audio_path: The recording to analyse.
        registry: Engine registry to use. Defaults to the application's.
        engines: Optional ``kind -> engine name`` overrides, e.g.
            ``{"chords": "chroma-baseline"}``. An unknown name raises
            :class:`~song_chord_lyrics_analyzer.utils.errors.EngineNotFoundError`.
        input_hash: Whether to record the SHA-256 of the input in provenance.
        chord_chunk_seconds: Analyse chords in windows of this length instead
            of one whole-file pass (roadmap Phase K: long songs). ``None`` -
            the default - keeps the one-pass behaviour every accuracy number in
            ``docs/ENGINE_COMPARISON.md`` was measured with. The windowing and
            its seam rules live in :mod:`song_chord_lyrics_analyzer.analysis.chunking`;
            only the chord layer is windowed, because the key and tempo
            engines need the whole song to answer at all and the lyrics engine
            chunks internally.
        chord_overlap_seconds: How much neighbouring chord windows share.
        on_progress: Called with a :class:`ProgressEvent` when a step starts
            and, for a windowed run, once per window. The callback runs on this
            thread and is never swallowed.

    Raises:
        AudioFileNotFoundError: When the file does not exist.
        UnsupportedAudioError: When it cannot be decoded as audio.
        DependencyError: When no engine at all can run in this environment.
        EngineNotFoundError: When an override names an unregistered engine.
        InputError: When the windowing options are impossible (raised before
            any engine runs). A chord engine that ignores the time range a
            window was analysed with fails its step instead - a warning and a
            partial run, like any other engine failure, never a duplicated
            timeline.
    """
    audio_path = Path(audio_path)
    selected = dict(engines or {})
    validate_windowing_options(chord_chunk_seconds, chord_overlap_seconds)
    engine_registry = registry if registry is not None else create_default_registry()

    document = probe_audio(audio_path)
    started_at = datetime.now(timezone.utc)

    steps: list[StepOutcome] = []
    warnings: list[str] = []
    errors: list[str] = []
    used: dict[str, EngineResult] = {}
    engine_infos: dict[str, Any] = {}
    configuration: dict[str, str] = {}

    for kind in SUPPORTED_KINDS:
        engine = _resolve(engine_registry, kind, selected.get(kind.value))
        if engine is None:
            steps.append(
                StepOutcome(kind.value, "(none)", StepStatus.SKIPPED, "no engine registered")
            )
            warnings.append(f"No {kind.value} engine is registered; that layer is missing.")
            continue
        configuration[kind.value] = engine.name
        _notify(on_progress, ProgressEvent(kind.value, engine.name, 0, 1))
        try:
            available = bool(engine.is_available())
        except Exception as error:  # availability must never crash the run
            available = False
            warnings.append(f"Engine {engine.name!r} availability check failed: {error}")
        if not available:
            steps.append(StepOutcome(kind.value, engine.name, StepStatus.SKIPPED, "not available"))
            warnings.append(
                f"Engine {engine.name!r} is not available; the {kind.value} layer is missing."
            )
            continue
        try:
            if kind is EngineKind.CHORDS and chord_chunk_seconds is not None:
                engine_result = analyze_chords_in_windows(
                    engine,
                    audio_path,
                    duration=document.duration,
                    chunk_seconds=chord_chunk_seconds,
                    overlap_seconds=chord_overlap_seconds,
                    on_window=_window_reporter(kind, engine.name, on_progress),
                )
                configuration["chords_chunk_seconds"] = _seconds_label(chord_chunk_seconds)
                if chord_overlap_seconds:
                    configuration["chords_overlap_seconds"] = _seconds_label(chord_overlap_seconds)
            else:
                engine_result = _call(engine, kind, audio_path)
        except SongLabError as error:
            steps.append(StepOutcome(kind.value, engine.name, StepStatus.FAILED, str(error)))
            warnings.append(f"{kind.value}: {error}")
            continue
        except Exception as error:  # engine bugs must not lose the other layers
            steps.append(StepOutcome(kind.value, engine.name, StepStatus.FAILED, str(error)))
            warnings.append(f"{kind.value}: engine {engine.name!r} failed: {error}")
            errors.append(f"{engine.name} failed on {audio_path.name}: {error}")
            _logger.debug("engine %s failed", engine.name, exc_info=True)
            continue
        steps.append(
            StepOutcome(
                kind.value,
                engine.name,
                StepStatus.OK,
                _describe(kind, engine_result),
                engine_result.processing_time_seconds,
            )
        )
        used[kind.value] = engine_result
        try:
            engine_infos[engine.name] = engine.engine_info()
        except Exception as error:  # metadata is best-effort, never fatal
            _logger.debug("could not read engine info of %r: %s", engine.name, error)

    if not any(step.status is StepStatus.OK for step in steps):
        reasons = "; ".join(f"{step.kind} ({step.engine}): {step.detail}" for step in steps)
        raise DependencyError(
            "No analysis engine could run in this environment.",
            hint=(
                f"{reasons}. Install the optional DSP stack (pip install numpy librosa) "
                "or add an engine; 'songlab doctor' lists what is registered."
            ),
        )

    result = AnalysisResult(
        provenance=Provenance(
            application_version=__version__,
            input_path=str(document.path),
            input_hash=compute_file_hash(document.path) if input_hash else None,
            python_version=platform.python_version(),
            platform=f"{platform.system()} {platform.machine()} / CPython {sys.version.split()[0]}",
            engines=engine_infos,
            configuration=configuration,
        ),
        audio=document,
        warnings=warnings,
    )
    for kind_name, engine_result in used.items():
        _merge(result, EngineKind(kind_name), engine_result)

    result.run = AnalysisRun(
        status=_status(steps),
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        steps=[
            f"{step.kind}:{step.engine}:{step.status.value}"
            + (f":{step.detail}" if step.detail else "")
            for step in steps
        ],
        warnings=warnings,
        errors=errors,
    )
    return AnalysisOutcome(result=result, steps=tuple(steps))
