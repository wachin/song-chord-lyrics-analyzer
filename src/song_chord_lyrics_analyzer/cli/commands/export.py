"""``songlab export`` - write the analysis of one song for musicians (Phase H).

The bridge between an analysed song and the formats musicians actually use.
The command holds no rendering logic: format selection lives here, rendering
lives in :mod:`song_chord_lyrics_analyzer.export`. The sidecar next to the
audio file, when one exists, is folded in first - the same stack the GUI saves
- so what a user exports is what they saw, edits included. ``--transpose`` and
``--simplify`` then transform the exported layer only - the roadmap's
CLI-first transpose workflow - and compose with saved edits instead of
fighting them.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from song_chord_lyrics_analyzer.analysis import run_analysis
from song_chord_lyrics_analyzer.app.editing import (
    ChordCommand,
    CommandStack,
    SimplifyChords,
    TransposeChords,
    effective_chords,
)
from song_chord_lyrics_analyzer.app.persistence import (
    edits_sidecar_path,
    load_edits,
    rebuild_stack,
)
from song_chord_lyrics_analyzer.export import EXPORT_FORMATS, export_document
from song_chord_lyrics_analyzer.models.analysis import AnalysisResult
from song_chord_lyrics_analyzer.models.music import ChordEvent
from song_chord_lyrics_analyzer.utils.errors import InputError
from song_chord_lyrics_analyzer.utils.logging import get_logger

__all__ = ["add_arguments", "run"]

_logger = get_logger("cli.export")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register ``songlab export`` arguments."""
    parser.add_argument("audio", type=Path, help="audio file whose analysis to export")
    parser.add_argument(
        "--format",
        choices=EXPORT_FORMATS,
        default="chordpro",
        help="output format (default: chordpro)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        metavar="FILE",
        help="write the export to this file",
    )
    parser.add_argument(
        "--transpose",
        type=int,
        default=None,
        metavar="SEMITONES",
        help=(
            "transpose every recognised chord by this offset (-11..+11) in the "
            "export; the analysis itself is never changed"
        ),
    )
    parser.add_argument(
        "--simplify",
        action="store_true",
        help="collapse extended chords to triads (Am7 -> Am) in the export",
    )


class ExportLayers(Protocol):
    """What the exporter's stack-shaped seam reads off the layers."""

    @property
    def effective(self) -> Sequence[ChordEvent]: ...

    @property
    def effective_lyrics(self) -> Sequence[Any]: ...


class _LayerView:
    """A read-only :class:`ExportLayers` over one fixed pair of layers."""

    def __init__(
        self,
        chords: Sequence[ChordEvent],
        lyrics: Sequence[Any] | None,
    ) -> None:
        self._chords = list(chords)
        self._lyrics = list(lyrics) if lyrics is not None else []

    @property
    def effective(self) -> Sequence[ChordEvent]:
        return self._chords

    @property
    def effective_lyrics(self) -> Sequence[Any]:
        return self._lyrics


def _saved_stack(audio: Path) -> CommandStack | None:
    """The saved edits of ``audio``, replayed; ``None`` when there is no sidecar."""
    sidecar = edits_sidecar_path(audio)
    if not sidecar.is_file():
        return None
    return rebuild_stack(load_edits(sidecar))


def _effective_layers(
    audio: Path,
    *,
    transpose: int | None,
    simplify: bool,
) -> tuple[AnalysisResult, ExportLayers | None]:
    """The document of ``audio`` plus the layer the user asked to export.

    The sidecar's edits, when saved, are replayed first; the command-line
    transforms are then applied on top. The returned layers are either the
    live replayed :class:`CommandStack` or a read-only :class:`ExportLayers`
    view - the exporter only reads ``effective``/``effective_lyrics``, which
    both provide.
    """
    outcome = run_analysis(audio, input_hash=False)
    document = outcome.result
    stack: CommandStack | None = _saved_stack(audio)
    if transpose is None and not simplify:
        return document, stack

    base = list(stack.effective) if stack is not None else list(document.chords)
    commands: list[ChordCommand] = []
    if transpose is not None:
        commands.append(TransposeChords(transpose))
    if simplify:
        commands.append(SimplifyChords())
    chords = effective_chords(base, commands)
    lyrics = stack.effective_lyrics if stack is not None else ()
    view: ExportLayers | None = _LayerView(chords, lyrics)
    return document, view


def run(args: argparse.Namespace) -> int:
    """Execute ``songlab export``."""
    if args.transpose is not None and not -11 <= args.transpose <= 11:
        raise InputError(
            f"--transpose must be within -11..+11, got {args.transpose!r}.",
            hint="An octave is the same music; use the in-octave offset.",
        )
    document, stack = _effective_layers(
        Path(args.audio),
        transpose=args.transpose,
        simplify=args.simplify,
    )
    chords = stack.effective if stack is not None and stack.effective else None
    lyrics = stack.effective_lyrics if stack is not None and stack.effective_lyrics else None
    written = export_document(
        document,
        args.format,
        args.output,
        chords=chords,
        lyrics=lyrics,
    )
    print(f"Exported {args.format} to {written}")
    return 0
