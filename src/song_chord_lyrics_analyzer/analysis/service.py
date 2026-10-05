"""Run the registered engines and assemble one canonical document.

Roadmap sections 8, 9, 61 and 62: an analysis is the canonical
:class:`~song_chord_lyrics_analyzer.models.analysis.AnalysisResult` plus the
:class:`~song_chord_lyrics_analyzer.models.analysis.Provenance` record that says
where every value came from. This service owns that assembly and nothing else -
no argument parsing, no formatting.

Three rules shape it:

* **A failing engine never destroys a document.** Chords, key and tempo are
  independent; if one fails the others are still kept, the failure becomes a
  warning, and the run is marked ``partial``. Only when *nothing* could run does
  the analysis fail.
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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer import __version__
from song_chord_lyrics_analyzer.audio.probe import compute_file_hash, probe_audio
from song_chord_lyrics_analyzer.engines.base import ChordAnalysisOptions, EngineKind
from song_chord_lyrics_analyzer.engines.registry import create_default_registry
from song_chord_lyrics_analyzer.models.analysis import (
    AnalysisResult,
    AnalysisRun,
    EngineResult,
    Provenance,
    RunStatus,
)
from song_chord_lyrics_analyzer.utils.errors import DependencyError, SongLabError
from song_chord_lyrics_analyzer.utils.logging import get_logger

__all__ = [
    "SUPPORTED_KINDS",
    "AnalysisOutcome",
    "StepOutcome",
    "StepStatus",
    "run_analysis",
]

_logger = get_logger("analysis")

#: Engine kinds this service runs today. Lyrics is deliberately absent: no
#: lyrics engine is registered yet, and pretending otherwise would put an empty
#: transcript in a document that claims to be analysed.
SUPPORTED_KINDS: tuple[EngineKind, ...] = (
    EngineKind.CHORDS,
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
    if kind is EngineKind.KEY:
        return engine.detect_key(audio_path, {})
    return engine.detect_tempo(audio_path, {})


def _describe(kind: EngineKind, result: EngineResult) -> str:
    """A one-line summary of what an engine produced."""
    if kind is EngineKind.CHORDS:
        return f"{len(result.chords)} chords"
    if kind is EngineKind.KEY:
        return f"key {result.key.label}" if result.key is not None else "no key"
    if result.tempo is None:
        return "no tempo"
    return f"{result.tempo.bpm:.1f} BPM"


def _merge(target: AnalysisResult, kind: EngineKind, result: EngineResult) -> None:
    """Copy one engine's canonical output into the document."""
    if kind is EngineKind.CHORDS:
        target.chords = list(result.chords)
    elif kind is EngineKind.KEY:
        target.key = result.key
    else:
        target.tempo = result.tempo
    if result.raw is not None:
        target.raw[result.engine] = result.raw


def _status(steps: list[StepOutcome]) -> RunStatus:
    """``partial`` when some step did not deliver, ``failed`` when none did."""
    ok = [step for step in steps if step.status is StepStatus.OK]
    if ok and len(ok) == len(steps):
        return RunStatus.SUCCEEDED
    if ok:
        return RunStatus.PARTIAL
    return RunStatus.FAILED


def run_analysis(
    audio_path: Path,
    *,
    registry: Any | None = None,
    engines: Mapping[str, str] | None = None,
    input_hash: bool = True,
) -> AnalysisOutcome:
    """Analyse ``audio_path`` and return the canonical document.

    Args:
        audio_path: The recording to analyse.
        registry: Engine registry to use. Defaults to the application's.
        engines: Optional ``kind -> engine name`` overrides, e.g.
            ``{"chords": "chroma-baseline"}``. An unknown name raises
            :class:`~song_chord_lyrics_analyzer.utils.errors.EngineNotFoundError`.
        input_hash: Whether to record the SHA-256 of the input in provenance.

    Raises:
        AudioFileNotFoundError: When the file does not exist.
        UnsupportedAudioError: When it cannot be decoded as audio.
        DependencyError: When no engine at all can run in this environment.
        EngineNotFoundError: When an override names an unregistered engine.
    """
    audio_path = Path(audio_path)
    selected = dict(engines or {})
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
