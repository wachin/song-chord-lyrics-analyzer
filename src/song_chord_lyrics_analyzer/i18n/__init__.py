"""Internationalization wiring for the window (roadmap sections 3, 77-79).

The application is English-first: the strings in the code *are* the source
catalogue, and a translated catalogue is a compiled Qt file
(``translations/song_chord_lyrics_analyzer_<code>.qm``) loaded at runtime
through ``QTranslator`` - the phase-17 workflow
``docs/INTERNATIONALIZATION.md`` records.

This package owns the wiring only, and it never guesses a language:

* English (:data:`SOURCE_LANGUAGE`) is the source and needs no catalogue; it
  is what the window shows until the user explicitly picks another installed
  one,
* :func:`available_languages` reports exactly what is installed on disk -
  nothing more, and never invents a display name for a catalogue it cannot
  name,
* :func:`install_translator` loads one catalogue onto a ``QApplication`` and
  raises when it is missing or unreadable: a window that silently stays
  English while claiming to be Spanish is the failure this module exists to
  prevent.

Qt is imported lazily, so the core install (no PyQt6) keeps this module
importable for its constants and discovery, and only the two functions that
need the GUI stack raise the project's honest
:class:`~song_chord_lyrics_analyzer.utils.errors.DependencyError`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from song_chord_lyrics_analyzer.utils.errors import DependencyError, InputError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PyQt6.QtCore import QTranslator

__all__ = [
    "LANGUAGES",
    "SOURCE_LANGUAGE",
    "SOURCE_LANGUAGE_NAME",
    "available_languages",
    "default_catalogue_dir",
    "install_translator",
    "language_name",
]

#: The source language. Its strings are the ones in the code, so it never
#: needs a catalogue file.
SOURCE_LANGUAGE = "en"

#: How the source language is named in its own language, for the menu.
SOURCE_LANGUAGE_NAME = "English"

#: Languages this application plans to offer, by code, named in their own
#: language. A language appears in the window only when its compiled
#: catalogue is actually installed - this map names them, it does not offer
#: them.
LANGUAGES: dict[str, str] = {
    "de": "Deutsch",
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "it": "Italiano",
    "pt": "Português",
}

#: Catalogue files follow the planned Qt Linguist naming: one compiled file
#: per language, next to the ``.ts`` source a translator works from.
_PREFIX = "song_chord_lyrics_analyzer_"
_SUFFIX = ".qm"


def _qt() -> Any:
    """The Qt modules, or the project's honest error for a Qt-free install."""
    try:
        from PyQt6 import QtCore
    except ImportError as error:  # pragma: no cover - only without the extra
        raise DependencyError(
            "Switching the window's language needs PyQt6, which is not installed.",
            hint='Install the optional GUI stack: pip install "song-chord-lyrics-analyzer[gui]"',
        ) from error
    return QtCore


def default_catalogue_dir() -> Path:
    """The ``translations/`` directory this checkout ships catalogues in.

    In the source tree that is the repository's own directory. An installed
    package has no such directory, so discovery finds nothing and the window
    honestly offers only English - a missing catalogue is never faked.
    """
    return Path(__file__).resolve().parents[3] / "translations"


def language_name(code: str) -> str:
    """The display name of ``code`` in its own language, or ``code`` itself."""
    return LANGUAGES.get(code, code)


def available_languages(directory: Path | None = None) -> tuple[tuple[str, str], ...]:
    """The ``(code, native name)`` pairs of the installed catalogues.

    Only files naming a known language are offered: a stray or misspelled
    ``.qm`` is not a language. The source language is never listed - it is
    always available and needs no file.

    Args:
        directory: Where to look; defaults to :func:`default_catalogue_dir`.

    Returns:
        The installed languages, ordered by code for a stable menu.
    """
    root = Path(directory) if directory is not None else default_catalogue_dir()
    installed: list[tuple[str, str]] = []
    for code, name in sorted(LANGUAGES.items()):
        if code == SOURCE_LANGUAGE:
            continue
        if (root / f"{_PREFIX}{code}{_SUFFIX}").is_file():
            installed.append((code, name))
    return tuple(installed)


def install_translator(
    app: Any,
    code: str,
    *,
    directory: Path | None = None,
) -> QTranslator:
    """Load language ``code``'s catalogue onto ``app``.

    Args:
        app: The ``QApplication`` receiving the translator.
        code: The language code, e.g. ``"es"``.
        directory: Where the catalogue lives; defaults to
            :func:`default_catalogue_dir`.

    Returns:
        The installed translator. **The caller must keep it alive**: Qt drops
        a translation the moment its translator is garbage-collected, and a
        window that silently fell back to English mid-sentence is exactly the
        dishonesty this project does not ship.

    Raises:
        DependencyError: When PyQt6 is not installed.
        InputError: When the language is unknown, is the source language, or
            its catalogue is missing or unreadable.
    """
    if code == SOURCE_LANGUAGE:
        raise InputError(
            "English is the source language and needs no catalogue.",
            hint="Pick a language with an installed catalogue, or add one to translations/.",
        )
    if code not in LANGUAGES:
        raise InputError(
            f"Unknown language: {code!r}",
            hint=f"Known languages: {', '.join(sorted(LANGUAGES))}.",
        )
    QtCore = _qt()
    root = Path(directory) if directory is not None else default_catalogue_dir()
    path = root / f"{_PREFIX}{code}{_SUFFIX}"
    translator = QtCore.QTranslator()
    if not translator.load(str(path)):
        raise InputError(
            f"Could not load the {language_name(code)} catalogue: {path}",
            hint="The file is missing or unreadable; compile it with lrelease from its .ts source.",
        )
    app.installTranslator(translator)
    return translator
