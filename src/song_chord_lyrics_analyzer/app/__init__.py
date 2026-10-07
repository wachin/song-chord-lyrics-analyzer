"""Application layer: the headless service behind the CLI and the GUI.

No Qt, no display code, no machine-learning imports. This package holds the
state a user session needs - which song, which chords, where the playhead is -
and the presenter that turns that state into something a front end can draw
(roadmap Phases C and D).
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

__all__ = [
    "DEFAULT_REFRESH_INTERVAL",
    "ConsoleDisplay",
    "DisplayFrame",
    "SessionSnapshot",
    "SongSession",
    "follow",
    "frame_from",
    "render_frame",
]
