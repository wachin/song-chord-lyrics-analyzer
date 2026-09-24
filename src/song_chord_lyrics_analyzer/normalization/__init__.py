"""Normalization layer (roadmap sections 13, 38, 71 and 90).

Normalization converts raw engine output into canonical events. Raw results are
never mutated in place: the pipeline keeps ``raw``, ``normalized`` and
``final`` representations separate.
"""

from __future__ import annotations

from song_chord_lyrics_analyzer.normalization.chords import (
    NO_CHORD_LABELS,
    ParsedChord,
    normalize_note_name,
    parse_chord_label,
    render_chord_label,
    transpose_chord_label,
    transpose_note_name,
)

__all__ = [
    "NO_CHORD_LABELS",
    "ParsedChord",
    "normalize_note_name",
    "parse_chord_label",
    "render_chord_label",
    "transpose_chord_label",
    "transpose_note_name",
]
