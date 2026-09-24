"""Allow ``python -m song_chord_lyrics_analyzer`` as an alternative to ``songlab``."""

from __future__ import annotations

import sys

from song_chord_lyrics_analyzer.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
