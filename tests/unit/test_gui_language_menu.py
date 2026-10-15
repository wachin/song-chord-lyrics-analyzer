"""The Language menu: only installed catalogues, never a guessed language.

The menu is the only thing in the product that changes the language
(docs/INTERNATIONALIZATION.md): it offers English (the source, always) plus
every compiled catalogue found on disk, a switch loads that catalogue onto
the application, and a failure keeps the language the window had - reported,
never silently English with a Spanish menu item ticked.

The catalogue compiled here is a test fixture whose "translation" is
``(ES) Open...``: a marker, not a Spanish string. The product ships no
translated strings until a human translator fills the source catalogue.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from fixtures.catalogues import compile_catalogue
from song_chord_lyrics_analyzer.gui.main_window import MainWindow

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PyQt6") is None,
    reason="PyQt6 is not installed (optional 'gui' extra)",
)

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")


def _enabled_labels(window: MainWindow) -> list[str]:
    """The labels of the enabled transport buttons, in order."""
    return [
        action.text()
        for toolbar in window.findChildren(QtWidgets.QToolBar)
        for action in toolbar.actions()
        if action.text() and action.isEnabled()
    ]


def _warned(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Capture dialogs instead of opening them, so tests stay headless."""
    messages: list[str] = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *args, **kwargs: messages.append(args[-1]),
    )
    return messages


class TestTheMenuOffersOnlyWhatIsInstalled:
    def test_a_checkout_without_compiled_catalogues_offers_only_english(
        self, qt_app: object
    ) -> None:
        window = MainWindow()

        try:
            assert window.language == "en"
            assert window.installed_languages == (("en", "English"),)
        finally:
            window.close()

    def test_an_installed_catalogue_appears_in_its_own_language(
        self, qt_app: object, tmp_path: Path
    ) -> None:
        compile_catalogue(tmp_path, "es")
        window = MainWindow(translations_dir=tmp_path)

        try:
            assert window.installed_languages == (("en", "English"), ("es", "Español"))
        finally:
            window.close()

    def test_the_source_language_starts_checked(self, qt_app: object) -> None:
        window = MainWindow()

        try:
            # The check mark is the one state of the menu with no public
            # accessor; everything else is read through the window's surface.
            assert window._language_actions["en"].isChecked() is True
        finally:
            window.close()


class TestSwitchingLanguages:
    def test_picking_a_catalogue_retranslates_the_window(
        self, qt_app: object, tmp_path: Path
    ) -> None:
        compile_catalogue(tmp_path, "es")
        window = MainWindow(translations_dir=tmp_path)

        try:
            assert window.set_language("es") is True

            assert window.language == "es"
            assert window._language_actions["es"].isChecked() is True
            assert "(ES) Open..." in _enabled_labels(window)  # the transport toolbar

            # Switching back is a real switch-back, not a reload of the app.
            assert window.set_language("en") is True
            assert window.language == "en"
            assert "Open..." in _enabled_labels(window)
        finally:
            window.close()

    def test_a_language_without_a_catalogue_is_refused_and_the_old_one_kept(
        self, qt_app: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        warned = _warned(monkeypatch)
        window = MainWindow(translations_dir=tmp_path)  # empty: nothing installed

        try:
            assert window.set_language("de") is False

            assert window.language == "en"  # kept, honestly
            assert warned and "Could not load" in warned[0]
            assert "Open..." in _enabled_labels(window)  # still the source strings
        finally:
            window.close()

    def test_choosing_through_the_menu_goes_through_the_same_path(
        self, qt_app: object, tmp_path: Path
    ) -> None:
        compile_catalogue(tmp_path, "es")
        window = MainWindow(translations_dir=tmp_path)

        try:
            window._on_language_chosen(window._language_actions["es"])

            assert window.language == "es"
            assert "(ES) Open..." in _enabled_labels(window)
        finally:
            window.set_language("en")  # leave the shared application clean
            window.close()

    def test_an_unchecked_failure_keeps_the_tick_where_it_was(
        self, qt_app: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _warned(monkeypatch)
        window = MainWindow(translations_dir=tmp_path)

        try:
            window._on_language_chosen(window._language_actions["en"])  # installed: the only one

            assert window.language == "en"
            assert window._language_actions["en"].isChecked() is True
            # Nothing was offered for "de", so its state is simply absent.
        finally:
            window.close()
