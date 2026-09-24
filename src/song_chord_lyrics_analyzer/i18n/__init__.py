"""Internationalization (roadmap sections 3, 77-79) - intentionally empty.

The application is English-first: identifiers, CLI help, errors, logs and
documentation stay in English until the English application is stable. Qt
Linguist, ``lupdate``/``lrelease`` and ``QTranslator`` are introduced in phase
17, together with the ``translations/`` catalogues.

Nothing in this package may hard-code translated strings for the GUI before
that point.
"""

from __future__ import annotations

__all__: list[str] = []
