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
from song_chord_lyrics_analyzer.engines.chroma_baseline import ChromaBaselineEngine
from song_chord_lyrics_analyzer.engines.decoding import viterbi_decode
from song_chord_lyrics_analyzer.engines.key_krumhansl import KrumhanslKeyEngine
from song_chord_lyrics_analyzer.engines.lyrics_chunking import (
    DEFAULT_CHUNK_SECONDS,
    Chunk,
    plan_chunks,
    reassemble,
)
from song_chord_lyrics_analyzer.engines.lyrics_parakeet import ParakeetLyricsEngine
from song_chord_lyrics_analyzer.engines.registry import (
    EngineRegistry,
    create_default_registry,
)
from song_chord_lyrics_analyzer.engines.tempo_librosa import LibrosaTempoEngine

__all__ = [
    "DEFAULT_CHUNK_SECONDS",
    "BaseEngine",
    "BeatEngine",
    "ChordAnalysisOptions",
    "ChordEngine",
    "ChromaBaselineEngine",
    "Chunk",
    "EngineKind",
    "EngineRegistry",
    "KeyEngine",
    "KrumhanslKeyEngine",
    "LibrosaTempoEngine",
    "LyricsEngine",
    "LyricsOptions",
    "ParakeetLyricsEngine",
    "StemSeparationEngine",
    "StemSeparationOptions",
    "TempoEngine",
    "create_default_registry",
    "plan_chunks",
    "reassemble",
    "viterbi_decode",
]
