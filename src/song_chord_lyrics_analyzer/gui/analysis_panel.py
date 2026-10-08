"""The analysis side panel: what was found, and where it came from (Phase D).

The panel is deliberately dumb. It receives the rows produced by
:func:`~song_chord_lyrics_analyzer.app.summary.summarize` and shows them in a
form, so the strings a user reads are the strings the presenter produced - and
the presenter is tested without a display.
"""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFormLayout, QLabel, QWidget

from song_chord_lyrics_analyzer.app.summary import SummaryRow

__all__ = ["AnalysisPanel"]


class AnalysisPanel(QWidget):
    """A form of ``label: value`` rows describing one analysis."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._form = QFormLayout(self)
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._rows: tuple[SummaryRow, ...] = ()

    @property
    def rows(self) -> tuple[SummaryRow, ...]:
        """The rows the panel was asked to show."""
        return self._rows

    def set_rows(self, rows: Sequence[SummaryRow]) -> None:
        """Replace every row with ``rows``."""
        self._rows = tuple(rows)
        self._clear()
        for row in rows:
            label = QLabel(f"{row.label}:")
            value = QLabel(row.value)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setWordWrap(True)
            self._form.addRow(label, value)

    def text_rows(self) -> tuple[tuple[str, str], ...]:
        """What is actually displayed: the ``(label, value)`` pairs on screen.

        Read back out of the widgets, so a test asserts the panel a user sees
        rather than the list it was handed.
        """
        pairs: list[tuple[str, str]] = []
        for index in range(self._form.rowCount()):
            label_item = self._form.itemAt(index, QFormLayout.ItemRole.LabelRole)
            value_item = self._form.itemAt(index, QFormLayout.ItemRole.FieldRole)
            if label_item is None or value_item is None:
                continue
            label_widget = label_item.widget()
            value_widget = value_item.widget()
            if isinstance(label_widget, QLabel) and isinstance(value_widget, QLabel):
                pairs.append((label_widget.text().rstrip(":"), value_widget.text()))
        return tuple(pairs)

    def _clear(self) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
