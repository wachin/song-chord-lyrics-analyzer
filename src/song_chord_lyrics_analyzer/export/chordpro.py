"""The ChordPro exporter (roadmap Phase H).

ChordPro is the text format musicians actually share: chord names sitting in
square brackets directly above the syllables they land on. The renderer is a
pure function of the document plus the effective (edited) layers, so the same
call a GUI makes after a transpose produces the same sheet a fresh analysis
would, and the output never claims fields the model does not have - there is
no invented key, no fabricated metadata directive, and lines the engine found
nothing for appear as plain lyric lines without chords.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Sequence

from song_chord_lyrics_analyzer.models.analysis import AnalysisResult
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment
from song_chord_lyrics_analyzer.models.music import ChordEvent

__all__ = ["chordpro_of"]

#: A lyric fragment containing a newline or tab must stay one printable
#: line, so control characters fold to their visible equivalents.
_SPACE_FOLD = str.maketrans({"\t": "    ", "\n": " ", "\r": " "})


def _word_timing(line: LyricSegment) -> list[tuple[str, float]]:
    """The words of ``line`` with a usable (start, ...) anchor each.

    Engine words all carry timestamps or none of them do; a line with only
    some timed falls back to the segment's own boundaries, spread evenly.
    """
    if line.has_word_timestamps and line.start is not None:
        return [(word.text, word.start) for word in line.words]  # type: ignore[misc]
    return []


def _fold(text: str) -> str:
    """Make a rendered fragment one printable line: newlines become spaces."""
    return text.translate(_SPACE_FOLD)


def render_chordpro(
    document: AnalysisResult,
    *,
    chords: Sequence[ChordEvent] | None = None,
    lyrics: Iterable[LyricSegment] | None = None,
) -> str:
    """Render ``document`` as a ChordPro sheet.

    Args:
        document: The canonical analysis (its audio path is the title).
        chords: The chord layer to place, defaulting to the document's. A
            session passes its *effective* layer here, so user edits (a
            transpose, a relabelled chord) print exactly as displayed.
        lyrics: The lyric layer to sing, defaulting to the document's.
    """
    events = document.chords if chords is None else list(chords)
    lines = document.lyrics if lyrics is None else list(lyrics)
    starts = [event.start for event in events]

    out: list[str] = []
    title = document.audio.path.name if document.audio is not None else "Unknown title"
    out.append(f"{{title: {title}}}")
    if document.key is not None:
        out.append(f"{{key: {document.key.label}}}")
    if document.tempo is not None:
        out.append(f"{{tempo: {document.tempo.bpm:.0f}}}")
    out.append("")

    for line in lines:
        if line.kind.value == "instrumental":
            out.append("{soc}")
            out.append("{eoc}")
            continue
        timings = _word_timing(line)
        if not timings:
            out.append(_fold(line.text))
            continue
        chunks: list[str] = []
        for index, (word, word_start) in enumerate(timings):
            # The chord sounding when the word starts, searched once per
            # word; a word in a gap carries no bracket at all.
            position = bisect_right(starts, word_start) - 1
            chord = ""
            if position >= 0:
                event = events[position]
                in_span = event.end is None or word_start < event.end
                if in_span and event.label:
                    chord = f"[{event.label}]"
            prefix = " " if index > 0 else ""
            chunks.append(f"{prefix}{chord}{word}")
        out.append("".join(chunks).rstrip())

    return "\n".join(out) + "\n"


# The module's single entry point keeps the exporter vocabulary explicit.
chordpro_of = render_chordpro
