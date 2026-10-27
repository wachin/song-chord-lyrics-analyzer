"""Application layer: the headless service behind the CLI and the GUI.

No Qt, no display code, no machine-learning imports. This package holds the
state a user session needs - which song, which chords, where the playhead is -
and the presenters that turn that state into something a front end can draw:
the frame for the current instant (`display`), the bands and the seconds/pixel
mapping of the whole timeline (`timeline`) and the analysis rows (`summary`).
Roadmap Phases C and D.
"""

from __future__ import annotations

import song_chord_lyrics_analyzer.app.chord_lyrics as _chord_lyrics
import song_chord_lyrics_analyzer.app.lyrics_view as _lyrics_view
from song_chord_lyrics_analyzer.app.chord_lyrics import (
    ChordLyricLine,
    PlacedChord,
    chord_lyric_lines,
)
from song_chord_lyrics_analyzer.app.display import (
    DEFAULT_REFRESH_INTERVAL,
    ConsoleDisplay,
    DisplayFrame,
    follow,
    frame_from,
    render_frame,
)
from song_chord_lyrics_analyzer.app.lyrics_view import lyric_at, lyric_lines, word_at
from song_chord_lyrics_analyzer.app.session import (
    ProgressReporter,
    SessionSnapshot,
    SongSession,
)
from song_chord_lyrics_analyzer.app.summary import SummaryRow, summarize
from song_chord_lyrics_analyzer.app.timeline import (
    ChordBand,
    chord_bands,
    position_for_x,
    x_for_position,
)

__all__ = [
    "DEFAULT_REFRESH_INTERVAL",
    "ChordBand",
    "ChordLyricLine",
    "ConsoleDisplay",
    "DisplayFrame",
    "PlacedChord",
    "ProgressReporter",
    "SessionSnapshot",
    "SongSession",
    "SummaryRow",
    "chord_bands",
    "chord_lyric_lines",
    "follow",
    "frame_from",
    "lyric_at",
    "lyric_lines",
    "position_for_x",
    "render_frame",
    "summarize",
    "word_at",
    "x_for_position",
]

#: Re-exported modules, so front ends can reach a presenter by one import.
chord_lyrics = _chord_lyrics
lyrics_view = _lyrics_view
