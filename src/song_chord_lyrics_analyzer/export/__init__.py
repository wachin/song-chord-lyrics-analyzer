"""Export stage (roadmap Phase H): render the canonical model for musicians.

Exporters are pure functions of the canonical document plus the effective
(edited) layers; the model never becomes ChordPro or Markdown itself, and no
exporter writes a field the model does not have. The formats:

* **JSON** - the canonical document, already what ``songlab analyze --json``
  prints and what :mod:`song_chord_lyrics_analyzer.schema.codec` round-trips;
  here it just gains the one entry point the CLI needs.
* **ChordPro** (:mod:`.chordpro`) - chord names in brackets over the words
  they land on, the format musicians share.
* **Markdown** (:mod:`.markdown`) - a readable sheet: header, chord table,
  lyrics.

Every exporter accepts the same ``chords``/``lyrics`` overrides, so a session
can pass its effective (edited) layer and print exactly what the user sees.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path

from song_chord_lyrics_analyzer.export.chordpro import chordpro_of, render_chordpro
from song_chord_lyrics_analyzer.export.markdown import markdown_of, render_markdown
from song_chord_lyrics_analyzer.models.analysis import AnalysisResult
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment
from song_chord_lyrics_analyzer.models.music import ChordEvent
from song_chord_lyrics_analyzer.schema.codec import encode

__all__ = [
    "EXPORT_FORMATS",
    "ExportFormat",
    "chordpro_of",
    "export_document",
    "markdown_of",
    "render_chordpro",
    "render_markdown",
    "render_json",
]

#: The formats ``songlab export`` accepts, in the order they print in help.
EXPORT_FORMATS: tuple[str, ...] = ("json", "chordpro", "markdown")

#: Alias the CLI validates against, so the error message names exactly them.
ExportFormat = str  # one of EXPORT_FORMATS; kept a name for the docstring


def render_json(
    document: AnalysisResult,
    *,
    chords: Sequence[ChordEvent] | None = None,
    lyrics: Iterable[LyricSegment] | None = None,
) -> str:
    """The canonical document as pretty-printed JSON, printed with edits when given.

    The ``chords``/``lyrics`` overrides replace the document's layers before
    encoding - the same seam the text renderers use, so an exported JSON can
    carry the transposed chord layer without rebuilding the document.
    """
    payload = encode(document)
    if chords is not None:
        payload = {**payload, "chords": [encode(event) for event in chords]}
    if lyrics is not None:
        payload = {**payload, "lyrics": [encode(line) for line in lyrics]}
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


def export_document(
    document: AnalysisResult,
    fmt: str,
    out: Path,
    *,
    chords: Sequence[ChordEvent] | None = None,
    lyrics: Iterable[LyricSegment] | None = None,
) -> Path:
    """Write ``document`` in ``fmt`` to ``out``; return the path written.

    Args:
        document: The canonical analysis.
        fmt: One of :data:`EXPORT_FORMATS`.
        out: Destination file. The suffix is not enforced - the user may be
            piping to a versioned name like ``sheet-v2.md``.
        chords: The effective chord layer (edits included), when one exists.
        lyrics: The effective lyric layer, when one exists.

    Raises:
        :class:`~utils.errors.InputError`: Unknown format.
    """
    from song_chord_lyrics_analyzer.utils.errors import InputError

    renderer = {
        "json": render_json,
        "chordpro": render_chordpro,
        "markdown": render_markdown,
    }.get(fmt)
    if renderer is None:
        raise InputError(
            f"Unknown export format: {fmt!r}.",
            hint=f"Supported formats: {', '.join(EXPORT_FORMATS)}.",
        )
    text = renderer(document, chords=chords, lyrics=lyrics)
    destination = Path(out)
    destination.write_text(text, encoding="utf-8")
    return destination
