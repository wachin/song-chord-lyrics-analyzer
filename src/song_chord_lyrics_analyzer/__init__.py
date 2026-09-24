"""Song Chord Lyrics Analyzer.

A cross-platform local music-analysis laboratory that extracts synchronized
lyrics, chords, beats, tempo and key from an audio file.

The package is intentionally layered (see ``docs/ARCHITECTURE.md``)::

    CLI / GUI
        -> application services
        -> analysis pipeline
        -> engine interfaces
        -> concrete engines
        -> canonical models

No concrete analysis engine may be imported at package import time, so that
importing :mod:`song_chord_lyrics_analyzer` stays fast and dependency-free.
"""

from __future__ import annotations

__all__ = [
    "__version__",
    "CLI_NAME",
    "PACKAGE_NAME",
    "PROJECT_NAME",
]

PROJECT_NAME = "song-chord-lyrics-analyzer"
PACKAGE_NAME = "song_chord_lyrics_analyzer"
CLI_NAME = "songlab"

#: Single source of truth for the application version. Packaging reads this
#: attribute via ``[tool.setuptools.dynamic]`` in ``pyproject.toml``.
__version__ = "0.1.0"
