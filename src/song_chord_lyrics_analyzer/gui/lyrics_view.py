"""The lyrics view: lyric lines with their chords above them, one clock.

A thin Qt widget over :mod:`song_chord_lyrics_analyzer.app.chord_lyrics` and
:mod:`song_chord_lyrics_analyzer.app.lyrics_view`, the same way
:class:`~song_chord_lyrics_analyzer.gui.timeline.TimelineWidget` is a thin
widget over :mod:`song_chord_lyrics_analyzer.app.timeline`: the widget decides
nothing about the clock or the alignment. It draws the rows the presenter
produced - each row is a **monospace** chord line and lyric line in one
paragraph, so a chord's character column is exactly above its word - and every
position update asks the session which segment and word are sounding now.

The chord row and the lyric row are separated by ``<br>``, so one drawn row is
still one ``QTextBlock``. That keeps the right-click mapping (block number ->
display index) exact even though each line is visually two lines tall: the
window's lyric commands address display indices, and a gap row maps to no line
at all and reports no index.

The active line is re-rendered bold, the active word is marked, and the active
chord is highlighted inside the chord row. All three come from the presenter
and the session, never from a second opinion computed in the widget.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QTextBrowser, QTextEdit, QVBoxLayout, QWidget

from song_chord_lyrics_analyzer.app.chord_lyrics import (
    ChordLyricLine,
    chord_lyric_lines,
)
from song_chord_lyrics_analyzer.app.lyrics_view import lyric_lines
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricSegmentKind, LyricWord
from song_chord_lyrics_analyzer.models.music import ChordEvent

__all__ = ["LyricsWidget"]


class LyricsWidget(QWidget):
    """Scrollable chord-over-lyric rows, with the current line and chord active.

    The widget holds no clock of its own: a caller (the window's refresh, a
    test) hands it the document once and then feeds it positions.
    """

    #: Shown when the open document carries no lyrics at all. The English
    #: reference, like :attr:`TimelineWidget.EMPTY_TEXT`: a test pins the
    #: widget's rendered placeholder against this literal.
    EMPTY_TEXT = "No lyrics for this song"

    #: A right-click on a line: the display index of the line under the
    #: pointer. The window turns that into the lyric commands' menu, exactly
    #: as the timeline turns its clicks into chord commands.
    line_menu_requested = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lines: tuple[LyricSegment, ...] = ()
        self._rows: tuple[ChordLyricLine, ...] = ()
        self._block_to_line: tuple[int | None, ...] = ()
        self._active: int | None = None
        self._active_word: str | None = None
        self._active_chord_start: float | None = None

        self._view = QTextBrowser(self)
        self._view.setOpenExternalLinks(False)
        self._view.setFrameShape(QTextBrowser.Shape.NoFrame)
        # A chord must stay over its word. Wrapping a long lyric line would
        # move the continuation under a chord row that no longer lines up, so
        # the chart scrolls horizontally instead and keeps the columns exact.
        self._view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._request_line_menu)
        self._placeholder = QLabel(self.EMPTY_TEXT, self)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        layout.addWidget(self._placeholder)

    # -- what to draw ------------------------------------------------------

    @property
    def lines(self) -> tuple[LyricSegment, ...]:
        """The lyric segments currently drawn, in display order."""
        return self._lines

    @property
    def rows(self) -> tuple[ChordLyricLine, ...]:
        """The drawn rows, chord rows and instrumental gaps included."""
        return self._rows

    @property
    def active_index(self) -> int | None:
        """Index of the highlighted segment, or ``None`` when nothing is active."""
        return self._active

    @property
    def active_word(self) -> str | None:
        """The word highlighted inside the active segment, or ``None``."""
        return self._active_word

    @property
    def active_chord_start(self) -> float | None:
        """Onset of the highlighted chord, or ``None`` when none is marked."""
        return self._active_chord_start

    def has_lyrics(self) -> bool:
        """Whether the drawn document carries any lyric line."""
        return bool(self._lines)

    def has_content(self) -> bool:
        """Whether anything at all is drawn (lyrics or chord-only rows)."""
        return bool(self._rows)

    def line_index_at(self, pos: QPoint) -> int | None:
        """The display index of the lyric line under ``pos``, or ``None``.

        One rendered paragraph is one row, so the text cursor's block number is
        a row index. A gap row (chords without lyrics) is not a lyric line and
        returns ``None``, so a right-click there opens no lyric-edit menu. A
        click past the last row is clamped to the last row, which is a lyric
        line in the ordinary case; if the document ends in an instrumental gap,
        there is still nothing to edit and the answer is ``None``.
        """
        row = self._row_at(pos)
        if row is None:
            return None
        return self._block_to_line[row]

    def _row_at(self, pos: QPoint) -> int | None:
        """The drawn row index under ``pos``, clamped to the document."""
        if not self._rows:
            return None
        block = self._view.cursorForPosition(pos).blockNumber()
        return max(0, min(block, len(self._rows) - 1))

    def _request_line_menu(self, pos: QPoint) -> None:
        """Re-emit the view's right-click as the lyric line it landed on."""
        index = self.line_index_at(pos)
        if index is not None:
            self.line_menu_requested.emit(index)

    def set_document(
        self,
        segments: tuple[LyricSegment, ...] | list[LyricSegment],
        chords: Sequence[ChordEvent] = (),
        *,
        prefer_flats: bool = False,
    ) -> None:
        """Draw the document's lyrics with ``chords`` seated above their words.

        Args:
            segments: The effective lyric layer (engine output plus edits).
            chords: The effective chord layer. Empty draws plain lyric lines,
                exactly the pre-chord view.
            prefer_flats: Respell chord roots/basses for a flat key.
        """
        self._lines = lyric_lines(segments)
        self._rows = chord_lyric_lines(self._lines, chords, prefer_flats=prefer_flats)
        index_by_identity = {id(segment): index for index, segment in enumerate(self._lines)}
        self._block_to_line = tuple(
            None if row.segment is None else index_by_identity.get(id(row.segment))
            for row in self._rows
        )
        self._active = None
        self._active_word = None
        self._active_chord_start = None
        self._placeholder.setVisible(not self._rows)
        self._view.setVisible(bool(self._rows))
        self._render()

    def set_active(
        self,
        segment: LyricSegment | None = None,
        word: LyricWord | None = None,
        chord: ChordEvent | None = None,
    ) -> None:
        """Highlight the caller's answers for the current playhead.

        The widget decides nothing about the clock: which line and which word
        are sounding is a session question (``SongSession.lyric_at`` and
        ``SongSession.word_at``, which mirror ``chord_at`` exactly), and which
        chord is current is the same frame the big chord label reads. The
        caller supplies all three and the widget only draws them. Calling it
        with no answers clears every highlight (nothing is claimed here).

        Args:
            segment: The active line, or ``None`` wherever no line is claimed.
            word: The active word inside ``segment``, or ``None``.
            chord: The chord event under the playhead, or ``None``.
        """
        index: int | None = None
        if segment is not None:
            with contextlib.suppress(ValueError):
                index = self._lines.index(segment)
        self._update_active(index, word if index is not None else None, chord)

    # -- rendering ---------------------------------------------------------

    def _update_active(
        self,
        index: int | None,
        word: LyricWord | None,
        chord: ChordEvent | None,
    ) -> None:
        """Adopt these answers, redrawing only when something actually changed."""
        word_text = word.text if word is not None else None
        chord_start = chord.start if chord is not None else None
        if (
            index != self._active
            or word_text != self._active_word
            or chord_start != self._active_chord_start
        ):
            self._active = index
            self._active_word = word_text
            self._active_chord_start = chord_start
            self._render()
        if index is not None:
            self._scroll_to(index)

    def _render(self) -> None:
        """Paint every row once; the active line, word and chord are marked."""
        if not self._rows:
            self._view.clear()
            return
        parts: list[str] = []
        for row_index, row in enumerate(self._rows):
            is_active = self._active is not None and self._block_to_line[row_index] == self._active
            chord_html = self._chord_html(row, is_active)
            text = self._escape(row.text).replace(" ", "&nbsp;")
            if row.is_gap or (
                row.segment is not None
                and row.segment.kind
                in (LyricSegmentKind.INSTRUMENTAL, LyricSegmentKind.NON_LEXICAL)
            ):
                text = f"<i>{text}</i>"
            if is_active:
                text = self._mark_word(text, self._active_word, row.segment, self._escape)
                parts.append(self._paragraph(chord_html, text, active=True))
            elif row.segment is None or row.segment.start is None:
                parts.append(self._paragraph(chord_html, text, dimmed=True))
            else:
                parts.append(self._paragraph(chord_html, text))
        self._view.setHtml("".join(parts))

    @staticmethod
    def _paragraph(
        chord_html: str, text_html: str, *, active: bool = False, dimmed: bool = False
    ) -> str:
        """One row as a single paragraph: optional chord line, then the lyric line."""
        style = "font-family: monospace; margin: 0 0 4px 0;"
        if active:
            style += " font-weight: bold;"
        elif dimmed:
            style += " color: palette(mid);"
        body = f"{chord_html}<br>{text_html}" if chord_html else text_html
        return f'<p style="{style}">{body}</p>'

    def _chord_html(self, row: ChordLyricLine, is_active: bool) -> str:
        """The monospace chord row, with the current chord highlighted."""
        if not row.chord_row:
            return ""
        if not is_active or self._active_chord_start is None:
            return self._escape(row.chord_row).replace(" ", "&nbsp;")
        for placed in row.chords:
            if placed.start != self._active_chord_start:
                continue
            before = row.chord_row[: placed.column]
            label = row.chord_row[placed.column : placed.column + len(placed.label)]
            after = row.chord_row[placed.column + len(placed.label) :]
            highlighted = (
                f'<span style="background-color: palette(highlight)">{self._escape(label)}</span>'
            )
            return (
                self._escape(before).replace(" ", "&nbsp;")
                + highlighted
                + self._escape(after).replace(" ", "&nbsp;")
            )
        return self._escape(row.chord_row).replace(" ", "&nbsp;")

    @staticmethod
    def _mark_word(
        text: str,
        word: str | None,
        segment: LyricSegment | None,
        escape: Callable[[str], str],
    ) -> str:
        """Wrap ``word`` inside already-escaped ``text`` in a highlight span."""
        if not word or segment is None:
            return text
        tokens = text.split(escape(word).replace(" ", "&nbsp;"))
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
        block = next(
            (position for position, line in enumerate(self._block_to_line) if line == index),
            0,
        )
        rows = len(self._rows)
        scrollbar.setValue(round(block / (rows - 1) * scrollbar.maximum()) if rows > 1 else 0)

    @staticmethod
    def _escape(text: str) -> str:
        """Escape ``text`` for a QTextBrowser paragraph - lyric text is data."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
