"""Analysis pipeline (roadmap sections 8, 9, 61 and 62).

Turns one audio file into the canonical
:class:`~song_chord_lyrics_analyzer.models.analysis.AnalysisResult` by running
the registered engines and recording where every value came from. The package
holds no argument parsing: the CLI command in
:mod:`song_chord_lyrics_analyzer.cli.commands.analyze` only presents the
outcome this service returns.

Two supporting modules carry the parts the service composes:

* :mod:`.progress` - the :class:`~.progress.ProgressEvent` a run reports while
  it works, so a long analysis is not a black box (roadmap Phase K);
* :mod:`.chunking` - windowed chord analysis for long audio, with the seam
  rules that make a windowed timeline continuous and deterministic.
"""

from __future__ import annotations

from song_chord_lyrics_analyzer.analysis.chunking import (
    DEFAULT_CHORD_CHUNK_SECONDS,
    analyze_chords_in_windows,
)
from song_chord_lyrics_analyzer.analysis.progress import ProgressEvent
from song_chord_lyrics_analyzer.analysis.service import (
    SUPPORTED_KINDS,
    AnalysisOutcome,
    StepOutcome,
    StepStatus,
    run_analysis,
    validate_windowing_options,
    with_lyrics_from_timed_text,
)

__all__ = [
    "DEFAULT_CHORD_CHUNK_SECONDS",
    "SUPPORTED_KINDS",
    "AnalysisOutcome",
    "ProgressEvent",
    "StepOutcome",
    "StepStatus",
    "analyze_chords_in_windows",
    "run_analysis",
    "validate_windowing_options",
    "with_lyrics_from_timed_text",
]
