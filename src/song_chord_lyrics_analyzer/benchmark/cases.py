"""Benchmark cases (roadmap section 46).

A benchmark directory holds one JSON case per song. Each case pairs a
**reference** (explicit ground truth, roadmap section 43) with a **hypothesis**
(whatever an engine produced) and carries the run's provenance. The metric
families are optional and independent, so a case computes only the metrics both
sides actually support:

``reference`` / ``hypothesis`` may each contain any of

```text
lyrics_text    a transcript string                     -> WER, CER
lyrics_words   [{"text": str, "start": float}, ...]    -> word timestamp error
chords         [{"start": float, "end": float, "label": str}, ...]
                                                       -> overlap / detection / timing
chord_labels   ["C", "G", ...]                         -> exact/root/quality/MIREX F1
key            "C major"                               -> relation, weighted score
tempo_bpm      120.0                                   -> absolute / half / double error
```

At the top level a case may declare ``"audio": "song.wav"`` (relative to the
case file). ``songlab benchmark --engine NAME`` then runs that engine on the
file — filling the hypothesis fields of the engine's own family (chord, key,
tempo or lyrics) plus the measured processing time and peak memory — while
cases without ``audio`` keep their stored hypothesis.

Nothing is invented: a missing field is simply not scored, and without
``--engine`` no engine runs here — this scores results that were already
produced.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.utils.errors import InputError

__all__ = ["BenchmarkCase", "load_case", "load_cases"]


@dataclass
class BenchmarkCase:
    """One song's reference/hypothesis pair plus its run provenance.

    ``audio`` optionally points at the recording the hypothesis should be
    (re)produced from: when present, ``songlab benchmark --engine NAME`` runs
    that engine on the file to fill the hypothesis and the measured run cost
    instead of trusting a stored one. The path is relative to the case file
    itself (``source``) unless absolute.
    """

    song: str
    reference: dict[str, Any]
    hypothesis: dict[str, Any]
    engine: str | None = None
    engine_version: str | None = None
    model: str | None = None
    duration_seconds: float | None = None
    processing_time_seconds: float | None = None
    peak_memory_bytes: int | None = None
    audio: str | None = None
    source: Path | None = None

    @property
    def engine_label(self) -> str:
        """The engine name, or ``"unknown"`` when the case did not record one."""
        return self.engine or "unknown"

    def audio_path(self) -> Path | None:
        """Resolve the case's audio field against the case file's directory.

        Relative paths are anchored where the case JSON lives, so a case
        directory stays portable. ``None`` when the case declares no audio.
        """
        if self.audio is None:
            return None
        path = Path(self.audio)
        if path.is_absolute() or self.source is None:
            return path
        return self.source.parent / path


def _require(mapping: dict[str, Any], field: str, source: Path) -> Any:
    if field not in mapping:
        raise InputError(
            f"Benchmark case {source} is missing the required field '{field}'.",
            hint=(
                "A case needs 'song', 'reference' and 'hypothesis'. "
                "See docs/BENCHMARK.md for the case format."
            ),
        )
    return mapping[field]


def load_case(path: Path) -> BenchmarkCase:
    """Load one benchmark case from a JSON file."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InputError(
            f"Benchmark case {path} is not valid JSON: {error}",
            hint="Fix the JSON syntax and try again.",
        ) from error
    if not isinstance(document, dict):
        raise InputError(
            f"Benchmark case {path} must be a JSON object.",
            hint="See docs/BENCHMARK.md for the case format.",
        )

    reference = _require(document, "reference", path)
    hypothesis = _require(document, "hypothesis", path)
    if not isinstance(reference, dict) or not isinstance(hypothesis, dict):
        raise InputError(
            f"Benchmark case {path} must have object 'reference' and 'hypothesis' blocks.",
            hint="See docs/BENCHMARK.md for the case format.",
        )

    return BenchmarkCase(
        song=str(_require(document, "song", path)),
        reference=reference,
        hypothesis=hypothesis,
        engine=document.get("engine"),
        engine_version=document.get("engine_version"),
        model=document.get("model"),
        duration_seconds=document.get("duration_seconds"),
        processing_time_seconds=document.get("processing_time_seconds"),
        peak_memory_bytes=document.get("peak_memory_bytes"),
        audio=document.get("audio"),
        source=path,
    )


def load_cases(directory: Path) -> list[BenchmarkCase]:
    """Load every ``*.json`` case in a directory, sorted by filename."""
    if not directory.exists():
        raise InputError(
            f"Benchmark directory not found: {directory}",
            hint="Pass a directory that contains benchmark case JSON files.",
        )
    if not directory.is_dir():
        raise InputError(
            f"Benchmark path is not a directory: {directory}",
            hint="Pass a directory that contains benchmark case JSON files.",
        )
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise InputError(
            f"No benchmark cases (*.json) found in {directory}",
            hint="Add at least one case file; see docs/BENCHMARK.md for the format.",
        )
    return [load_case(path) for path in paths]
