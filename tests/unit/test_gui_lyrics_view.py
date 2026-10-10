"""The offscreen lyrics view of the window (``[F]`` item 1).

The spec: active ``LyricSegment`` lines on the same clock as the chord band, a
word highlighted when its timestamps exist. The window is driven the way a user
drives it - open a file, move the playhead - with the fake player and fake
analysis the other GUI tests already use, so every assertion is exact.

One fake document, drawn and then fed positions like the window's refresh does:
before the first line nothing is active, inside a line its word is highlighted,
in a gap nothing is, and the dimmed untimed line never becomes active.
"""

from __future__ import annotations

import importlib.util

import pytest

from song_chord_lyrics_analyzer.gui.lyrics_view import LyricsWidget

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PyQt6") is None,
    reason="PyQt6 is not installed (optional 'gui' extra)",
)

pytest.importorskip("PyQt6.QtWidgets")


def _word(text: str, start: float | None, end: float | None = None):
    from song_chord_lyrics_analyzer.models.lyrics import LyricWord

    return LyricWord(text=text, start=start, end=end)


def _segment(text: str, start: float | None, end: float | None = None, words=()):
    from song_chord_lyrics_analyzer.models.lyrics import LyricSegment

    return LyricSegment(text=text, start=start, end=end, words=list(words))


DOCUMENT = (
    _segment(
        "hola mundo",
        0.0,
        2.0,
        [_word("hola", 0.0, 1.0), _word("mundo", 1.0, 2.0)],
    ),
    _segment("post-coro", None),  # untimed: drawn after, never active
    _segment(
        "adios amor",
        3.0,
        4.5,
        [_word("adios", 3.0, 3.8), _word("amor", 3.8, 4.5)],
    ),
)


class TestTheDocument:
    def test_an_empty_document_shows_the_placeholder(self, qt_app: object) -> None:
        view = LyricsWidget()

        view.set_document(())

        assert view.has_lyrics() is False
        assert view.lines == ()
        assert view.active_index is None

    def test_the_document_is_drawn_in_display_order(self, qt_app: object) -> None:
        view = LyricsWidget()

        view.set_document(DOCUMENT)

        assert [line.text for line in view.lines] == ["hola mundo", "adios amor", "post-coro"]
        assert view.has_lyrics() is True
        assert view.active_index is None


class TestTheClock:
    def test_at_the_start_the_first_line_is_active_with_its_first_word(
        self, qt_app: object
    ) -> None:
        view = LyricsWidget()
        view.set_document(DOCUMENT)

        view.set_playhead(0.0)

        assert view.active_index == 0
        assert view.active_word == "hola"

    def test_inside_a_line_the_line_and_its_word_are_active(self, qt_app: object) -> None:
        view = LyricsWidget()
        view.set_document(DOCUMENT)

        view.set_playhead(1.5)

        assert view.active_index == 0
        assert view.active_word == "mundo"

    def test_a_gap_between_lines_deactivates_the_previous_one(self, qt_app: object) -> None:
        view = LyricsWidget()
        view.set_document(DOCUMENT)
        view.set_playhead(1.5)
        assert view.active_index == 0

        view.set_playhead(2.5)

        assert view.active_index is None

    def test_the_second_timed_line_activates_with_its_word(self, qt_app: object) -> None:
        view = LyricsWidget()
        view.set_document(DOCUMENT)

        view.set_playhead(4.0)

        assert view.active_index == 1
        assert view.active_word == "amor"

    def test_the_untimed_line_never_activates(self, qt_app: object) -> None:
        view = LyricsWidget()
        view.set_document(DOCUMENT)

        for position in (0.0, 2.5, 6.0):
            view.set_playhead(position)
            assert view.active_index != 2

    def test_a_negative_playhead_is_clamped_like_the_timeline_clamps(self, qt_app: object) -> None:
        view = LyricsWidget()
        view.set_document(DOCUMENT)

        view.set_playhead(-0.5)

        assert view.active_index == 0
        assert view.active_word == "hola"
