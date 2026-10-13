"""The Markdown exporter (roadmap Phase H).

A readable, tabular rendering of the analysis: a header (title, key, tempo),
a chord list in playback order and the lyrics. Pure function of the
document plus the effective (edited) layers, exactly like the ChordPro
exporter, so both print the same state a session is showing.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from song_chord_lyrics_analyzer.models.analysis import AnalysisResult
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment
from song_chord_lyrics_analyzer.models.music import ChordEvent

__all__ = ["markdown_of", "render_markdown"]


def _fold(text: str) -> str:
    """Keep each lyric line on one table row: newlines become spaces."""
    return text.replace("\n", " ").replace("\r", " ").replace("\t", "    ")


def _time(seconds: float | None) -> str:
    """A column-friendly timestamp, or an empty cell."""
    if seconds is None:
        return ""
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes):02d}:{rest:05.2f}"


def render_markdown(
    document: AnalysisResult,
    *,
    chords: Sequence[ChordEvent] | None = None,
    lyrics: Iterable[LyricSegment] | None = None,
) -> str:
    """Render ``document`` as Markdown.

    Args:
        document: The canonical analysis (its audio path is the title).
        chords: The chord layer to list, defaulting to the document's. A
            session passes its *effective* layer here, so edits print as
            displayed.
        lyrics: The lyric layer to render, defaulting to the document's.
    """
    events = document.chords if chords is None else list(chords)
    lines = document.lyrics if lyrics is None else list(lyrics)

    out: list[str] = []
    title = document.audio.path.name if document.audio is not None else "Unknown title"
    out.append(f"# {title}")
    facts: list[str] = []
    if document.key is not None:
        facts.append(f"key {document.key.label}")
    if document.tempo is not None:
        facts.append(f"tempo {document.tempo.bpm:.0f} BPM")
    if document.audio is not None and document.audio.duration is not None:
        facts.append(f"duration {_time(document.audio.duration)}")
    if facts:
        out.append("")
        out.append("* " + " · ".join(facts))
    out.append("")

    if events:
        out.append("## Chords")
        out.append("")
        out.append("| start | end | chord |")
        out.append("| ----- | --- | ----- |")
        for event in events:
            out.append(f"| {_time(event.start)} | {_time(event.end)} | {event.label} |")
        out.append("")

    if lines:
        out.append("## Lyrics")
        out.append("")
        for line in lines:
            timestamp = _time(line.start)
            if line.kind.value == "instrumental":
                out.append(f"**[instrumental{(' ' + timestamp) if timestamp else ''}]**")
            elif timestamp:
                out.append(f"`{timestamp}` — {_fold(line.text)}")
            else:
                out.append(_fold(line.text))
        out.append("")

    return "\n".join(out)


#: Alias kept for symmetry with the chordpro module's public name.
markdown_of = render_markdown
