"""Analysis pipeline (roadmap sections 8, 9, 61 and 62).

Turns one audio file into the canonical
:class:`~song_chord_lyrics_analyzer.models.analysis.AnalysisResult` by running
the registered engines and recording where every value came from. The package
holds no argument parsing: the CLI command in
:mod:`song_chord_lyrics_analyzer.cli.commands.analyze` only presents the
outcome this service returns.
"""

from __future__ import annotations

from song_chord_lyrics_analyzer.analysis.service import (
    SUPPORTED_KINDS,
    AnalysisOutcome,
    StepOutcome,
    StepStatus,
    run_analysis,
)

__all__ = [
    "SUPPORTED_KINDS",
    "AnalysisOutcome",
    "StepOutcome",
    "StepStatus",
    "run_analysis",
]
