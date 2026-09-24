"""Engine layer.

Concrete engines are adapters behind the protocols in :mod:`engines.base` and
are discovered through :class:`engines.registry.EngineRegistry`.
"""

from __future__ import annotations

from song_chord_lyrics_analyzer.engines.base import (
    BaseEngine,
    BeatEngine,
    ChordAnalysisOptions,
    ChordEngine,
    EngineKind,
    KeyEngine,
    LyricsEngine,
    LyricsOptions,
    StemSeparationEngine,
    StemSeparationOptions,
    TempoEngine,
)
from song_chord_lyrics_analyzer.engines.registry import (
    EngineRegistry,
    create_default_registry,
)

__all__ = [
    "BaseEngine",
    "BeatEngine",
    "ChordAnalysisOptions",
    "ChordEngine",
    "EngineKind",
    "EngineRegistry",
    "KeyEngine",
    "LyricsEngine",
    "LyricsOptions",
    "StemSeparationEngine",
    "StemSeparationOptions",
    "TempoEngine",
    "create_default_registry",
]
