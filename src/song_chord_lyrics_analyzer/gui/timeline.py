"""The drawn timeline: waveform, chord strip and playhead (roadmap Phase D).

This is the one widget that paints rather than arranges:

* the **waveform** comes from the peaks the session reduced the decoded samples
  to, drawn at true amplitude - a quiet recording looks quiet;
* the **chord strip** below it comes from
  :func:`~song_chord_lyrics_analyzer.app.timeline.chord_bands`, so every label
  drawn is the label ``SongSession.chord_at`` would report at that instant;
* the **playhead** is placed with the same presenter, which is what keeps the
  line, the strip and the session in agreement.

Clicking or dragging anywhere in the widget asks the session to seek: the widget
emits :attr:`TimelineWidget.seek_requested` and holds no state of its own beyond
what it was told to draw.
"""

from __future__ import annotations

from PyQt6.QtCore import QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPainter, QPaintEvent
from PyQt6.QtWidgets import QSizePolicy, QWidget

from song_chord_lyrics_analyzer.app.timeline import (
    ChordBand,
    position_for_x,
    x_for_position,
)
from song_chord_lyrics_analyzer.audio.peaks import WaveformPeaks

__all__ = ["TimelineWidget"]


class TimelineWidget(QWidget):
    """Waveform, chord strip and playhead over one track.

    Signals:
        seek_requested: Emitted with a position in seconds when the user clicks
            or drags the timeline.
    """

    seek_requested = pyqtSignal(float)

    #: Height of the chord strip under the waveform, in pixels.
    STRIP_HEIGHT = 24

    #: Shown before a song is open.
    EMPTY_TEXT = "Open a song to see its waveform, its chords and the playhead"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._peaks: WaveformPeaks | None = None
        self._bands: tuple[ChordBand, ...] = ()
        self._duration = 0.0
        self._position = 0.0
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click or drag to seek")

    # -- what to draw ------------------------------------------------------

    @property
    def peaks(self) -> WaveformPeaks | None:
        """The waveform currently drawn, or ``None``."""
        return self._peaks

    @property
    def bands(self) -> tuple[ChordBand, ...]:
        """The chord bands currently drawn, in time order."""
        return self._bands

    @property
    def duration(self) -> float:
        """Length of the drawn track in seconds, ``0.0`` when unknown."""
        return self._duration

    @property
    def position(self) -> float:
        """Playhead of the drawn frame, in seconds."""
        return self._position

    def set_peaks(self, peaks: WaveformPeaks | None) -> None:
        """Draw this waveform."""
        self._peaks = peaks
        self.update()

    def set_bands(self, bands: tuple[ChordBand, ...]) -> None:
        """Draw these chord bands in the strip under the waveform."""
        self._bands = tuple(bands)
        self.update()

    def set_duration(self, duration: float) -> None:
        """Set the length of the drawn track, in seconds."""
        self._duration = max(0.0, float(duration))
        self.update()

    def set_playhead(self, position: float, duration: float) -> None:
        """Move the playhead and refresh the track length in one call."""
        self._position = max(0.0, float(position))
        self._duration = max(0.0, float(duration))
        self.update()

    # -- geometry ----------------------------------------------------------

    def seconds_at(self, x: float) -> float:
        """The playback position at ``x`` pixels from the left edge."""
        return position_for_x(x, duration=self._duration, width=self._pixel_width())

    def x_at(self, seconds: float) -> float:
        """Where ``seconds`` sits, in pixels from the left edge."""
        return x_for_position(seconds, duration=self._duration, width=self._pixel_width())

    def _pixel_width(self) -> float:
        """The drawn width, never zero: an unshown widget still has geometry."""
        return float(max(1, self.width()))

    # -- interaction -------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        """Seek to the clicked position."""
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self._seek_to(event.position().x())

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        """Seek while the left button is held down, so a drag scrubs."""
        if event is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._seek_to(event.position().x())

    def _seek_to(self, x: float) -> None:
        if self._duration <= 0.0:
            return
        self.seek_requested.emit(self.seconds_at(x))

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event: QPaintEvent | None) -> None:
        """Draw the waveform, the chord strip and the playhead."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().base())
        if self._duration <= 0.0:
            painter.setPen(self.palette().mid().color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.EMPTY_TEXT)
            painter.end()
            return

        strip_height = min(self.STRIP_HEIGHT, max(1, self.height() // 3))
        wave = QRect(0, 0, self.width(), max(1, self.height() - strip_height))
        strip = QRect(0, wave.height(), self.width(), strip_height)
        self._draw_waveform(painter, wave)
        self._draw_bands(painter, strip)
        self._draw_playhead(painter)
        painter.end()

    def _draw_waveform(self, painter: QPainter, wave: QRect) -> None:
        peaks = self._peaks
        if peaks is None or peaks.is_empty:
            return
        middle = wave.center().y()
        half = max(1.0, wave.height() / 2.0 - 1.0)
        painter.setPen(self.palette().text().color())
        pairs = zip(peaks.minimums, peaks.maximums, strict=True)
        for index, (low, high) in enumerate(pairs):
            x = wave.x() + int(index * wave.width() / peaks.bucket_count)
            top = middle - round(high * half)
            bottom = middle - round(low * half)
            # A silent column still shows the baseline instead of vanishing.
            painter.drawLine(x, min(top, bottom), x, max(top, bottom))

    def _draw_bands(self, painter: QPainter, strip: QRect) -> None:
        painter.fillRect(strip, self.palette().alternateBase())
        metrics = painter.fontMetrics()
        for index, band in enumerate(self._bands):
            left = self.x_at(band.start)
            right = self.x_at(band.end)
            box = QRectF(left, float(strip.y()), max(1.0, right - left), float(strip.height()))
            if band.is_silence:
                background = self.palette().mid().color()
                foreground = self.palette().text().color()
            elif index % 2:
                background = self.palette().alternateBase().color()
                foreground = self.palette().text().color()
            else:
                background = self.palette().highlight().color()
                foreground = self.palette().highlightedText().color()
            painter.fillRect(box, background)
            if box.width() >= metrics.horizontalAdvance(band.label) + 6:
                painter.setPen(foreground)
                painter.drawText(box, Qt.AlignmentFlag.AlignCenter, band.label)

    def _draw_playhead(self, painter: QPainter) -> None:
        x = round(self.x_at(self._position))
        painter.setPen(self.palette().highlight().color())
        painter.drawLine(x, 0, x, self.height() - 1)
