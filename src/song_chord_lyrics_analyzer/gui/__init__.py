"""The desktop window: a client of the application layer (roadmap Phase D).

The window is the last layer of the architecture, not the first:

``PyQt6 widgets`` → ``app/ session + presenters`` → ``engines``

so nothing in this package imports an engine, ``librosa``, numpy or an
``analysis/`` internal, and nothing here re-derives synchronization: the widgets
render the `DisplayFrame`, the `ChordBand`s and the `SummaryRow`s the application
layer already produced.

PyQt6 is an optional extra. Importing this package never imports Qt, so the core
install stays dependency-free and the CI gate keeps working without it; calling
:func:`run` without PyQt6 raises the same honest
:class:`~song_chord_lyrics_analyzer.utils.errors.DependencyError` the rest of the
project raises for a missing optional dependency.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from pathlib import Path

from song_chord_lyrics_analyzer.utils.errors import DependencyError

__all__ = ["require_qt", "run"]

_QT_HINT = (
    'Install the optional GUI stack (pip install "song-chord-lyrics-analyzer[gui]") '
    "to open the desktop window. The terminal display needs no Qt: "
    "'songlab play AUDIO' shows the same chord under the same playhead."
)


def require_qt() -> None:
    """Check that PyQt6 can be imported, or explain how to install it.

    Raises:
        DependencyError: When PyQt6 is not installed.
    """
    try:
        importlib.import_module("PyQt6.QtWidgets")
    except ImportError as error:
        raise DependencyError(
            "The desktop window needs PyQt6, which is not installed.",
            hint=_QT_HINT,
        ) from error


def run(
    audio: str | Path | None = None,
    *,
    engines: Mapping[str, str] | None = None,
    input_hash: bool = True,
    argv: list[str] | None = None,
) -> int:
    """Open the application window and run it until the user closes it.

    Args:
        audio: Optional audio file to open straight away.
        engines: Optional ``kind -> engine name`` overrides for the analysis.
        input_hash: Whether opening a file records its SHA-256 in provenance.
        argv: Arguments passed on to ``QApplication``.

    Returns:
        The exit code of the event loop.

    Raises:
        DependencyError: When PyQt6 is not installed.
    """
    require_qt()
    from song_chord_lyrics_analyzer.gui.main_window import launch

    return launch(audio, engines=engines, input_hash=input_hash, argv=argv)
