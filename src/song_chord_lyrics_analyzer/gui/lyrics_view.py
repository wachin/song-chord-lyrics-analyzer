"""The lyrics view: the lines of a document, the active one highlighted.

A thin Qt widget over :mod:`song_chord_lyrics_analyzer.app.lyrics_view`, the
same way :class:`~song_chord_lyrics_analyzer.gui.timeline.TimelineWidget` is a
thin widget over :mod:`song_chord_lyrics_analyzer.app.timeline`: the widget
decides nothing about the clock. It draws the display order
:func:`~song_chord_lyrics_analyzer.app.lyric_lines` produces, and every
position update asks :func:`~song_chord_lyrics_analyzer.app.lyric_at` and
:func:`~song_chord_lyrics_analyzer.app.lyrics_view.word_at` which segment and
which word are sounding now - so the highlighted line on screen is the line
the presenter claims for that instant, never a second opinion.

The active line is re-rendered bold and the active word is marked inside it;
both come from the presenter, in a re-render instead of a cursor offset into
HTML, because the offset arithmetic is exactly the kind of widget logic this
layer is not allowed to grow. An untimed segment is drawn after the timed
ones, dimmed, and never becomes active.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QTextBrowser, QVBoxLayout, QWidget

from song_chord_lyrics_analyzer.app.lyrics_view import lyric_at, lyric_lines, word_at
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricSegmentKind

__all__ = ["LyricsWidget"]

#: Shown when the open document carries no lyrics at all.
EMPTY_TEXT = "No lyrics for this song"


class LyricsWidget(QWidget):
    """Scrollable lyric lines over the document, with the current one active.

    The widget holds no clock of its own: a caller (the window's refresh, a
    test) hands it the document once and then feeds it positions.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lines: tuple[LyricSegment, ...] = ()
        self._active: int | None = None
        self._active_word: str | None = None

        self._view = QTextBrowser(self)
        self._view.setOpenExternalLinks(False)
        self._view.setFrameShape(QTextBrowser.Shape.NoFrame)
        self._placeholder = QLabel(EMPTY_TEXT, self)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        layout.addWidget(self._placeholder)

    # -- what to draw ------------------------------------------------------

    @property
    def lines(self) -> tuple[LyricSegment, ...]:
        """The segments currently drawn, in display order."""
        return self._lines

    @property
    def active_index(self) -> int | None:
        """Index of the highlighted segment, or ``None`` when nothing is active."""
        return self._active

    @property
    def active_word(self) -> str | None:
        """The word highlighted inside the active segment, or ``None``."""
        return self._active_word

    def has_lyrics(self) -> bool:
        """Whether the drawn document carries any lyric line."""
        return bool(self._lines)

    def set_document(self, segments: tuple[LyricSegment, ...] | list[LyricSegment]) -> None:
        """Draw the segments of the open document, in display order."""
        self._lines = lyric_lines(segments)
        self._active = None
        self._active_word = None
        self._placeholder.setVisible(not self._lines)
        self._view.setVisible(bool(self._lines))
        self._render()

    def set_playhead(self, position: float) -> None:
        """Highlight the segment and the word sounding at ``position`` seconds.

        A negative position is clamped to the start, like the timeline does.
        """
        position = max(0.0, float(position))
        segment = lyric_at(self._lines, position)
        index = self._lines.index(segment) if segment is not None else None
        word = word_at(segment, position) if segment is not None else None
        if index != self._active or (word.text if word else None) != self._active_word:
            self._active = index
            self._active_word = word.text if word is not None else None
            self._render()
        if index is not None:
            self._scroll_to(index)

    # -- rendering ---------------------------------------------------------

    def _render(self) -> None:
        """Paint every line once; the active one is marked in the HTML."""
        if not self._lines:
            self._view.clear()
            return
        parts: list[str] = []
        for index, segment in enumerate(self._lines):
            text = self._escape(segment.text or " ".join(word.text for word in segment.words))
            if segment.kind in (LyricSegmentKind.INSTRUMENTAL, LyricSegmentKind.NON_LEXICAL):
                text = f"<i>{text}</i>"
            if index == self._active:
                text = self._mark_word(text, self._active_word, segment, self._escape)
                parts.append(f'<p style="font-weight: bold">{text}</p>')
            elif segment.start is None:
                parts.append(f'<p style="color: palette(mid)">{text}</p>')
            else:
                parts.append(f"<p>{text}</p>")
        self._view.setHtml("".join(parts))

    @staticmethod
    def _mark_word(
        text: str,
        word: str | None,
        segment: LyricSegment,
        escape: Callable[[str], str],
    ) -> str:
        """Wrap ``word`` inside already-escaped ``text`` in a highlight span."""
        if not word:
            return text
        tokens = text.split(escape(word))
        if len(tokens) < 2:
            return text
        return (
            '<span style="background-color: palette(highlight)">escape_placeholder</span>'.replace(
                "escape_placeholder", escape(word)
            ).join(tokens)
        )

    def _scroll_to(self, index: int) -> None:
        """Keep the active line visible without jumping when the user scrolls."""
        scrollbar = self._view.verticalScrollBar()
        if scrollbar is None:  # an unshown widget has no scroll backing store
            return
        lines_per_step = max(1, len(self._lines) - 1)
        scrollbar.setValue(
            round(index / lines_per_step * scrollbar.maximum()) if len(self._lines) else 0
        )

    @staticmethod
    def _escape(text: str) -> str:
        """Escape ``text`` for a QTextBrowser paragraph - lyric text is data."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
