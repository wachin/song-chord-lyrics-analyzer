"""The ``.lrc`` parser - the karaoke timed-text format, read honestly (Phase F).

LRC is the format musicians already share, so an ``.lrc`` file becomes the
lyric base exactly as the file says, with every rule a real file exercises:

* ``[mm:ss.xx]`` timestamps open a line, in 1-3 digit minutes and a fraction
  of 1-3 digits. The fraction is padded **on the right** to milliseconds
  (``1:12.5`` is 1:12,500, the truncated-hundredths writers emit), never
  parsed as a decimal number.
* Several timestamps before one text repeat that text at each timestamp -
  the format's own convention for repeated lines.
* ``[offset:±ms]`` shifts every timestamp; a positive value delays the file's
  claims against the audio, the direction the spec defines.
* Metadata tags (``[ti:...]``, ``[ar:...]``, ...) and any other bracket tag
  are annotations, not lyrics - they never become segments. Tags that
  arrive concatenated on one line (``[ti:X][ar:Y]``) are consumed as
  annotations too, until something that is not a tag starts the text.
* The enhanced (A2) form ``line <mm:ss.xx>word <mm:ss.xx>word`` carries word
  timestamps. A word runs until the next word stamp; the last word of a line
  runs until the line's own end (the next line's start), because the singer
  does not stop there either.
* A line's ``end`` is the next line's ``start``; the file says nothing after
  the last line, so the last line stays open-ended the way the session's
  ``lyric_at`` expects. A stamp with no text after it is skipped - guessing
  an instrumental region from silence is fabrication.
* Text lines without any timestamp are kept as untimed lines; they stay
  visible, addressed by display index, but never activate on the clock.
* Lines that come out of order keep their file order when they start
  together (a stable sort by start time puts everything into playback
  order, which is what the LRC's own list order means).

Zero-dependency like the rest of the core: regex over the decoded text.
"""

from __future__ import annotations

import re
from pathlib import Path

from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricWord
from song_chord_lyrics_analyzer.utils.errors import InputError

__all__ = ["parse_lrc", "parse_lrc_text"]

#: ``[mm:ss.f{1,3}]``: 1-3 digit minutes, 1-2 digit seconds, optional fraction.
#: Deliberately narrow: anything without exactly this shape is a tag, not a
#: timestamp to guess around.
_TIMESTAMP = re.compile(
    r"\[(?P<minutes>\d{1,3}):(?P<seconds>\d{1,2})(?:\.(?P<fraction>\d{1,3}))?\]"
)

#: The line-level ``[offset:±ms]`` tag, the only metadata tag that changes data.
_OFFSET = re.compile(r"\[offset:(?P<sign>[+-])?\s*(?P<milliseconds>\d+)\]", re.IGNORECASE)

#: A metadata tag: a bracketed annotation of reasonable length. Anything that
#: matched no timestamp and looks like ``[...]`` on its own is one of these.
_TAG = re.compile(r"^\[[^]]{1,64}\]$")

#: ``<mm:ss.xx>`` inside a line, the enhanced A2 word stamp.
_WORD_STAMP = re.compile(r"<(?P<minutes>\d{1,3}):(?P<seconds>\d{1,2})(?:\.(?P<fraction>\d{1,3}))?>")

_WHITESPACE = re.compile(r"\s+")


def _seconds(minutes: str, seconds: str, fraction: str | None) -> float:
    """A parsed ``mm:ss.fr`` stamp as seconds, the fraction padded to ms."""
    total = int(minutes) * 60.0 + int(seconds)
    if fraction:
        total += int(fraction) * 10 ** (3 - len(fraction)) / 1000.0
    return total


def _stamps_of(line: str) -> list[float]:
    """Every leading timestamp of ``line``, including repeated ones."""
    starts: list[float] = []
    cursor = 0
    while True:
        match = _TIMESTAMP.match(line, cursor)
        if match is None:
            break
        starts.append(_seconds(match["minutes"], match["seconds"], match["fraction"]))
        cursor = match.end()
    return starts


def _stamps_end_of(line: str) -> int:
    """Where the leading timestamp block of ``line`` ends (0 when none)."""
    cursor = 0
    while True:
        match = _TIMESTAMP.match(line, cursor)
        if match is None:
            break
        cursor = match.end()
    return cursor


def _line_content(raw: str) -> tuple[str, list[tuple[float, str]]]:
    """Clean segment text and the enhanced ``(start, word)`` stamps of ``raw``.

    A stamp marks the text that follows it up to the next stamp - the A2
    convention. Empty pieces between two stamps mean a stamp with no word;
    they are skipped rather than turned into fabricated words.
    """
    matches = list(_WORD_STAMP.finditer(raw))
    stamps: list[tuple[float, int, int]] = [
        (
            _seconds(match["minutes"], match["seconds"], match["fraction"]),
            match.start(),
            match.end(),
        )
        for match in matches
    ]
    clean = _WHITESPACE.sub(" ", _WORD_STAMP.sub(" ", raw)).strip()
    words: list[tuple[float, str]] = []
    for index, (start, _open, close) in enumerate(stamps):
        following = stamps[index + 1][1] if index + 1 < len(stamps) else len(raw)
        piece = raw[close:following].strip()
        if piece:
            words.append((start, piece))
    return clean, words


_ANNOTATION = re.compile(r"^\[[^]]{1,64}\]")


def _annotations_consumed(line: str) -> str:
    """Re ``line`` without its leading bracket annotations.

    A line that is only annotations (``[ti:...][ar:...]`` - tags are usually
    one per line, but concatenated ones exist in the wild) returns empty and
    is skipped; whatever survives the brackets is the line's own text.
    """
    rest = line
    while True:
        stripped = rest.strip()
        annotation = _ANNOTATION.match(stripped)
        if annotation is None or _TIMESTAMP.match(stripped) is not None:
            return stripped
        rest = stripped[annotation.end() :]


def parse_lrc_text(text: str, *, name: str = "lyrics.lrc") -> list[LyricSegment]:
    """Parse the decoded text of an ``.lrc`` file into lyric segments.

    Args:
        text: The file's text, decoded UTF-8 (BOM tolerated upstream).
        name: The file's name, used inside error messages only.

    Returns:
        The segments in playback order; untimed lines (if the file carries
        any) sort to the end, exactly where
        :func:`~song_chord_lyrics_analyzer.app.lyrics_view.lyric_lines`
        displays them.

    Raises:
        :class:`~song_chord_lyrics_analyzer.utils.errors.InputError`: The file
            holds no lyric line at all.
    """
    offset_seconds = 0.0
    entries: list[tuple[float | None, tuple[str, list[tuple[float, str]]]]] = []
    for line in text.splitlines():
        stamped = _stamps_of(line)
        body = line[_stamps_end_of(line) :].strip()
        if not stamped:
            if not body:
                continue  # a blank line separates nothing in LRC
            offset_tag = _OFFSET.match(line.strip()) if body.startswith("[offset:") else None
            if offset_tag is not None:  # read before annotation-consume would swallow it
                sign = 1 if offset_tag["sign"] != "-" else -1
                offset_seconds = int(offset_tag["milliseconds"]) * sign / 1000.0
                continue
            stripped = _annotations_consumed(line)
            if not stripped:
                continue  # a line that is only annotations is metadata
            if _TAG.fullmatch(stripped):
                continue  # any other tag is metadata, not a lyric line
            entries.append((None, _line_content(stripped)))
            continue
        # A repeated text under several stamps becomes one segment per stamp:
        # the file repeats the same words at different times.
        for start in stamped:
            entries.append((round(start + offset_seconds, 3), _line_content(body)))
    if not entries:
        raise InputError(
            f"{name} holds no lyric lines.",
            hint=(
                "The file must carry [mm:ss.xx] timestamped lines or plain "
                "text lines; here only blank space and unknown tags were found."
            ),
        )
    timed = sorted((one for one in entries if one[0] is not None), key=lambda one: one[0] or 0.0)
    ordered: list[tuple[float | None, tuple[str, list[tuple[float, str]]]]] = timed + [
        one for one in entries if one[0] is None
    ]
    segments: list[LyricSegment] = []
    for index, (line_start, (text, stamps)) in enumerate(ordered):
        later = [one for one in ordered[index + 1 :] if one[0] is not None]
        end = later[0][0] if later else None
        segments.append(
            LyricSegment(
                text=text,
                start=line_start,
                end=end,
                words=_words_from(stamps, end),
                source="lrc",
            )
        )
    return segments


def _words_from(stamps: list[tuple[float, str]], line_end: float | None) -> list[LyricWord]:
    """Word models from ``[(start, text), ...]``; ends run to the next start.

    The final word of the line inherits the line's own end - the next line's
    start is the only later boundary the file carries. An open-ended line
    (the file's last one) leaves its last word open too: missing precision is
    never fabricated.
    """
    words: list[LyricWord] = []
    for index, (start, text) in enumerate(stamps):
        following = stamps[index + 1][0] if index + 1 < len(stamps) else line_end
        words.append(LyricWord(text=text, start=start, end=following, source="lrc"))
    return words


def parse_lrc(path: str | Path) -> list[LyricSegment]:
    """Read the ``.lrc`` file at ``path`` and parse it."""
    return parse_lrc_text(read_text(path), name=Path(path).name)


def read_text(path: str | Path) -> str:
    """Decoded file text; a UTF-8 BOM is tolerated, another encoding reported."""
    target = Path(path)
    try:
        raw = target.read_bytes()
    except OSError as error:
        raise InputError(
            f"Could not read {target}: {error}",
            hint="Check that the lyric file exists and is readable.",
        ) from error
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InputError(
            f"{target.name} is not UTF-8 text.",
            hint=("Re-save the lyric file as UTF-8; text encodings are never guessed around."),
        ) from error
