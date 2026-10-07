"""Application layer: the headless service behind the CLI and the GUI.

No Qt, no display code, no machine-learning imports. This package holds the
state a user session needs - which song, which chords, where the playhead is -
so that a front end only has to render it (roadmap Phases C and D).
"""

from __future__ import annotations

from song_chord_lyrics_analyzer.app.session import SessionSnapshot, SongSession

__all__ = [
    "SessionSnapshot",
    "SongSession",
]
