"""The ``.srt`` parser - SubRip titles, read honestly (Phase F).

SubRip files carry what the karaoke LRC does not: separate start and end
times per block, and sometimes none at all. The rules the parser keeps:

* A block is ``[index line]`` + ``start --> end`` + the text. The index is
  unreliable in real files (some omit it, some restart it), so blocks are
  only required to carry their timing line; a missing or repeated index is
  not an error.
* Times are ``HH:MM:SS,mmm`` - the comma is the format's own separator, but
  files written with a dot are accepted too. Hours are two digits, the
  fraction is padded **on the right** to milliseconds (``",5`` is 500 ms,
  the truncated writers emit), never parsed as a decimal number.
* Trailing junk after the arrow (position markers like ``X1:...``, or an
  ``h:mm:ss`` variant) is ignored - it annotates the timing, not the text.
* A block's internal line breaks become single spaces, because a lyric
  segment is one display line. Double spaces and trimming keep the file's
  words, not its spacing.
* An end before its start raises - the model already rejects it, and a
  subtitle timing bug is reported, not silently normalized.
* A block whose text is empty is skipped: an SRT silence marker is an
  annotation, not a lyric. Blocks that are entirely garbage (no ``-->``)
  are skipped for the same reason; a ``-->`` that does not parse is a
  reported error, because the file claims a timing it does not carry.
* Zero timed blocks produce an ``InputError``: a lyric base of nothing is
  not a lyric base.

Zero-dependency like the rest of the core: regex over the decoded text.
"""

from __future__ import annotations

import re
from pathlib import Path

from song_chord_lyrics_analyzer.alignment.lrc import read_text
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment
from song_chord_lyrics_analyzer.utils.errors import InputError

__all__ = ["parse_srt", "parse_srt_text"]

#: ``HH:MM:SS,mmm`` - comma as written, dot accepted when a file was written
#: sloppily. Hours are fixed two digits; the ms fraction is padded on the right.
_TIMED = re.compile(
    r"(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d{2})[,.](?P<fraction>\d{1,3})"
)
_ARROW = "-->"


def _seconds(hours: str, minutes: str, seconds: str, fraction: str | None) -> float:
    """A parsed ``HH:MM:SS,mmm`` stamp as seconds, the fraction padded to ms."""
    total = int(hours) * 3600.0 + int(minutes) * 60.0 + int(seconds)
    if fraction:
        total += int(fraction) * 10 ** (3 - len(fraction)) / 1000.0
    return total


def _timings_of(line: str) -> tuple[float, float]:
    """``start --> end`` of a timing line, in seconds.

    Raises:
        InputError: When the line carries the arrow but no valid timing pair.
    """
    if _ARROW not in line:
        raise AssertionError("caller guarantees the arrow")
    times = _TIMED.findall(line)
    if len(times) < 2:
        raise InputError(
            f"Subtitle timing {line.strip()!r} cannot be parsed.",
            hint="SRT timings are written '00:01:02,500 --> 00:01:06,000'.",
        )
    start = _seconds(*times[0])
    end = _seconds(*times[1])
    if end < start:
        raise InputError(
            f"Subtitle block ends ({end:.3f} s) before it starts ({start:.3f} s).",
            hint="Re-time the block; inverted timings are reported, never normalized.",
        )
    return start, end


def parse_srt_text(text: str, *, name: str = "lyrics.srt") -> list[LyricSegment]:
    """Parse the decoded text of an ``.srt`` file into lyric segments.

    Args:
        text: The file's text, decoded UTF-8 (BOM tolerated upstream).
        name: The file's name, used inside error messages only.

    Returns:
        The segments in file order (SubRip blocks are already in playback
        order; a file that is not is sorted into playback order, stably).

    Raises:
        :class:`~song_chord_lyrics_analyzer.utils.errors.InputError`: The file
            carries no subtitle block at all.
    """
    segments: list[LyricSegment] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        timing_lines = [line for line in lines if _ARROW in line]
        if not timing_lines:
            continue  # a block without a timing is annotation, not a lyric
        start, end = _timings_of(timing_lines[0])
        text_lines = [
            line for line in lines if line is not timing_lines[0] and not line.lstrip().isdigit()
        ]
        body = " ".join(text_lines).strip()
        if not body:
            continue  # empty text: a silence marker, never a made lyric
        segments.append(LyricSegment(text=body, start=start, end=end, source="srt"))
    if not segments:
        raise InputError(
            f"{name} holds no subtitle blocks.",
            hint="The file must carry 'start --> end' timing blocks with text.",
        )
    segments.sort(key=lambda segment: segment.start or 0.0)
    return segments


def parse_srt(path: str | Path) -> list[LyricSegment]:
    """Read the ``.srt`` file at ``path`` and parse it."""
    return parse_srt_text(read_text(path), name=Path(path).name)
