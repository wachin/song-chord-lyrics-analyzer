"""Canonical typed data model.

These dataclasses are the single internal representation of a song analysis.
Markdown, ChordPro, MIDI and MusicXML are outputs, never the model itself.
"""

from __future__ import annotations

from song_chord_lyrics_analyzer.models.analysis import (
    AlignmentResult,
    AnalysisResult,
    AnalysisRun,
    EngineInfo,
    EngineResult,
    Provenance,
    RunStatus,
)
from song_chord_lyrics_analyzer.models.audio import AudioDocument
from song_chord_lyrics_analyzer.models.confidence import (
    ConfidenceLevel,
    ConfidenceScore,
    level_for_value,
)
from song_chord_lyrics_analyzer.models.lyrics import (
    LyricSegment,
    LyricSegmentKind,
    LyricWord,
)
from song_chord_lyrics_analyzer.models.music import (
    CHORD_QUALITY_SUFFIX,
    NOTE_NAME_TO_PITCH_CLASS,
    PITCH_CLASS_NAMES,
    BarEvent,
    BeatEvent,
    ChordEvent,
    ChordQuality,
    DownbeatEvent,
    KeyEstimate,
    KeyMode,
    NoteEvent,
    Stem,
    StemName,
    TempoEstimate,
)

__all__ = [
    "CHORD_QUALITY_SUFFIX",
    "NOTE_NAME_TO_PITCH_CLASS",
    "PITCH_CLASS_NAMES",
    "AlignmentResult",
    "AnalysisResult",
    "AnalysisRun",
    "AudioDocument",
    "BarEvent",
    "BeatEvent",
    "ChordEvent",
    "ChordQuality",
    "ConfidenceLevel",
    "ConfidenceScore",
    "DownbeatEvent",
    "EngineInfo",
    "EngineResult",
    "KeyEstimate",
    "KeyMode",
    "LyricSegment",
    "LyricSegmentKind",
    "LyricWord",
    "NoteEvent",
    "Provenance",
    "RunStatus",
    "Stem",
    "StemName",
    "TempoEstimate",
    "level_for_value",
]
