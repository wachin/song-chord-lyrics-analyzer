"""Compile a small Qt Linguist catalogue for a test (i18n, phase 17).

A language only exists for the window when its compiled ``.qm`` is on disk,
so every test that needs an "installed" language builds one here with
``lrelease``. The strings are marked test fixtures - ``(es) Open...`` - not
translations: the product ships no translated strings until a human
translator fills the source catalogue (see docs/INTERNATIONALIZATION.md).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

__all__ = ["compile_catalogue"]

_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="{code}">
<context>
    <name>{context}</name>
    <message>
        <source>{source}</source>
        <translation>({tag}) {source}</translation>
    </message>
</context>
</TS>
"""


def compile_catalogue(
    directory: Path,
    code: str = "es",
    *,
    source: str = "Open...",
    context: str = "MainWindow",
) -> Path:
    """Write and compile ``song_chord_lyrics_analyzer_<code>.qm`` in ``directory``.

    Args:
        directory: Where the catalogue files are written.
        code: The language code the file is named after.
        source: The English string the catalogue translates.
        context: The Qt context (the class name) the string belongs to.

    Returns:
        The path of the compiled ``.qm`` file.

    Raises:
        pytest.skip.Exception: When ``lrelease`` is not installed - the test
            is then about the machine, not about the code.
    """
    lrelease = shutil.which("lrelease")
    if lrelease is None:
        pytest.skip("lrelease is not installed (Qt Linguist tooling missing)")
    ts = directory / f"song_chord_lyrics_analyzer_{code}.ts"
    ts.write_text(
        _TEMPLATE.format(code=code, context=context, source=source, tag=code.upper()),
        encoding="utf-8",
    )
    qm = directory / f"song_chord_lyrics_analyzer_{code}.qm"
    subprocess.run(
        [lrelease, str(ts), "-qm", str(qm)],
        check=True,
        capture_output=True,
    )
    return qm
