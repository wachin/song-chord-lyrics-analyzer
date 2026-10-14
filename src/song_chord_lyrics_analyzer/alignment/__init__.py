"""Alignment stage (roadmap sections 36, 37, 91 and Phase F).

Two responsibilities live here; the first is the delivered one:

* **External timed text** (Phase F, delivered): when lyrics come from a
  file instead of the ASR engine, :func:`parse_timed_text` reads a ``.lrc``
  (karaoke) or ``.srt`` (SubRip) file into the same
  :class:`~song_chord_lyrics_analyzer.models.lyrics.LyricSegment` rows the
  engine produces. The alignment rules of each format are documented where
  they are applied (see :mod:`.lrc` and :mod:`.srt`); nothing outside this
  package parses those files, and no parser rewrites what the file says.
* **Timeline fusion** (reserved, not implemented): placing lyrics, chords,
  beats, downbeats and bars on one shared timeline. The future entry point
  is ``align_events(...) -> AlignmentResult``; the
  :class:`~song_chord_lyrics_analyzer.models.analysis.AlignmentResult`
  model already exists to receive its output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from song_chord_lyrics_analyzer.alignment.lrc import parse_lrc_text
from song_chord_lyrics_analyzer.alignment.lrc import read_text as read_transcript
from song_chord_lyrics_analyzer.alignment.srt import parse_srt_text
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment
from song_chord_lyrics_analyzer.utils.errors import InputError

__all__ = [
    "TIMED_TEXT_SUFFIXES",
    "TranscriptParser",
    "parse_timed_text",
    "parse_timed_text_file",
]

#: The external lyric formats, in the order the error hints name them.
TIMED_TEXT_SUFFIXES: tuple[str, ...] = (".lrc", ".srt")


class TranscriptParser(Protocol):
    """How a format parser is called: decoded text in, lyric rows out."""

    def __call__(self, text: str, *, name: str) -> list[LyricSegment]: ...


#: The suffixes never guessed around: what the name says, the parser obeys.
TRANSCRIPT_PARSERS: dict[str, TranscriptParser] = {
    ".lrc": parse_lrc_text,
    ".srt": parse_srt_text,
}


def parse_timed_text_file(path: str | Path) -> list[LyricSegment]:
    """Read ``path`` and parse it, by its suffix, into lyric segments.

    The suffix decides the format and is never second-guessed against the
    content: a renamed file is reported, not auto-detected.

    Raises:
        :class:`~utils.errors.InputError`: Unknown format, unreadable file,
            undecodable text, or a file that carries no lyric line at all.
    """
    target = Path(path)
    suffix = target.suffix.lower()
    parser = TRANSCRIPT_PARSERS.get(suffix)
    if parser is None:
        supported = ", ".join(TIMED_TEXT_SUFFIXES)
        raise InputError(
            f"Cannot parse {target.name}: unknown lyric format {suffix!r}.",
            hint=f"Supported formats: {supported}.",
        )
    return parser(read_transcript(target), name=target.name)


def parse_timed_text(path: str | Path) -> tuple[LyricSegment, ...]:
    """The lyric base of one external timed-text file, in playback order.

    Both front ends call this one entry point; the model rows are exactly
    what the file claims (source ``"lrc"``/``"srt"``, confidence unknown),
    so the GUI edits, the sidecar persistence and the ChordPro/Markdown
    exporters treat them like any engine lyric base.
    """
    return tuple(parse_timed_text_file(path))
