"""The i18n wiring: catalogue discovery and loading, never guessing a language.

The application is English-first (docs/INTERNATIONALIZATION.md), so what is
under test here is the honesty of the wiring as much as the mechanics:

* English is the source language and never needs a catalogue file,
* a language appears for the window only when its compiled ``.qm`` is
  actually installed - a planned language in a dict is not an installed
  language,
* a load failure raises instead of silently keeping English,
* the checkout ships no catalogue at all while the English interface is still
  changing (docs/INTERNATIONALIZATION.md), so the window offers only English.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from fixtures.catalogues import compile_catalogue
from song_chord_lyrics_analyzer.i18n import (
    SOURCE_LANGUAGE,
    SOURCE_LANGUAGE_NAME,
    available_languages,
    default_catalogue_dir,
    install_translator,
    language_name,
)
from song_chord_lyrics_analyzer.utils.errors import InputError

HAS_QT = importlib.util.find_spec("PyQt6") is not None


class TestTheSourceLanguage:
    def test_the_source_is_english(self) -> None:
        assert SOURCE_LANGUAGE == "en"
        assert SOURCE_LANGUAGE_NAME == "English"

    def test_the_source_is_never_listed_even_with_catalogues_installed(
        self, tmp_path: Path
    ) -> None:
        compile_catalogue(tmp_path, "es")

        assert all(code != SOURCE_LANGUAGE for code, _name in available_languages(tmp_path))

    def test_the_source_is_refused_because_it_needs_no_catalogue(self) -> None:
        with pytest.raises(InputError, match="source language"):
            install_translator(_FakeApp(), "en")


class TestDiscovery:
    def test_no_catalogues_means_no_languages(self, tmp_path: Path) -> None:
        assert available_languages(tmp_path) == ()

    def test_an_installed_catalogue_is_offered_in_its_own_language(self, tmp_path: Path) -> None:
        compile_catalogue(tmp_path, "es")

        assert available_languages(tmp_path) == (("es", "Español"),)

    def test_a_file_for_an_unknown_language_is_not_a_language(self, tmp_path: Path) -> None:
        compile_catalogue(tmp_path, "xx")

        assert available_languages(tmp_path) == ()

    def test_installed_languages_come_in_a_stable_order(self, tmp_path: Path) -> None:
        compile_catalogue(tmp_path, "es")
        compile_catalogue(tmp_path, "de")

        assert [code for code, _name in available_languages(tmp_path)] == ["de", "es"]

    def test_an_unknown_code_is_named_by_its_code(self) -> None:
        assert language_name("xx") == "xx"
        assert language_name("es") == "Español"

    def test_the_default_directory_is_the_checkouts_translations(self) -> None:
        assert default_catalogue_dir().name == "translations"
        assert default_catalogue_dir().is_dir()

    def test_no_catalogue_ships_before_the_english_interface_is_frozen(self) -> None:
        """The policy: extraction starts after the freeze, so nothing is here yet.

        A planner's ``.ts`` path in the docs is a plan, not a shipped file: this
        checkout carries neither a translator's source catalogue nor a compiled
        one, which is exactly why the window offers only the source language.
        """
        root = default_catalogue_dir()
        assert root.is_dir()
        assert list(root.glob("*.ts")) == []
        assert list(root.glob("*.qm")) == []
        assert available_languages(root) == ()


class TestLoading:
    def test_an_unknown_language_is_refused_with_what_is_known(self) -> None:
        with pytest.raises(InputError, match="Unknown language"):
            install_translator(_FakeApp(), "xx")

    @pytest.mark.skipif(not HAS_QT, reason="PyQt6 is not installed (optional 'gui' extra)")
    def test_a_missing_catalogue_is_reported_instead_of_silently_keeping_english(
        self, qt_app: object, tmp_path: Path
    ) -> None:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        assert app is not None

        with pytest.raises(InputError, match="Could not load"):
            install_translator(app, "es", directory=tmp_path)

    @pytest.mark.skipif(not HAS_QT, reason="PyQt6 is not installed (optional 'gui' extra)")
    def test_a_compiled_catalogue_is_installed_and_translates(
        self, qt_app: object, tmp_path: Path
    ) -> None:
        from PyQt6.QtCore import QCoreApplication
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        assert app is not None
        compile_catalogue(tmp_path, "es")

        translator = install_translator(app, "es", directory=tmp_path)
        try:
            assert QCoreApplication.translate("MainWindow", "Open...") == "(ES) Open..."
        finally:
            app.removeTranslator(translator)
        assert QCoreApplication.translate("MainWindow", "Open...") == "Open..."


class _FakeApp:
    """An ``installTranslator`` sink, for the checks that need no Qt stack."""

    def __init__(self) -> None:
        self.installed: list[object] = []

    def installTranslator(self, translator: object) -> bool:
        self.installed.append(translator)
        return True
