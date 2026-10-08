"""Application layer: the headless service behind the CLI and the GUI.

No Qt, no display code, no machine-learning imports. This package holds the
state a user session needs - which song, which chords, where the playhead is -
and the presenters that turn that state into something a front end can draw:
the frame for the current instant (`display`), the bands and the seconds/pixel
mapping of the whole timeline (`timeline`) and the analysis rows (`summary`).
Roadmap Phases C and D.
"""

from __future__ import annotations

from song_chord_lyrics_analyzer.app.display import (
    DEFAULT_REFRESH_INTERVAL,
    ConsoleDisplay,
    DisplayFrame,
    follow,
    frame_from,
    render_frame,
)
from song_chord_lyrics_analyzer.app.session import SessionSnapshot, SongSession
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
    "ConsoleDisplay",
    "DisplayFrame",
    "SessionSnapshot",
    "SongSession",
    "SummaryRow",
    "chord_bands",
    "follow",
    "frame_from",
    "position_for_x",
    "render_frame",
    "summarize",
    "x_for_position",
]
