"""Unit tests for cross-platform path handling (roadmap sections 4 and 105)."""

from __future__ import annotations

from pathlib import Path

from song_chord_lyrics_analyzer.utils.paths import (
    CACHE_ENV_VAR,
    DATA_ENV_VAR,
    TEMP_ENV_VAR,
    default_cache_dir,
    default_data_dir,
    default_export_dir,
    default_model_dir,
    default_temp_dir,
    ensure_directory,
    resolve_output_path,
)


class TestDefaultDirectories:
    def test_defaults_are_absolute_and_namespaced(self) -> None:
        for directory in (default_cache_dir(), default_data_dir(), default_temp_dir()):
            assert directory.is_absolute()
        assert "songlab" in str(default_cache_dir()).lower()
        assert "songlab" in str(default_data_dir()).lower()

    def test_model_and_export_dirs_live_under_data_dir(self) -> None:
        assert default_model_dir() == default_data_dir() / "models"
        assert default_export_dir() == default_data_dir() / "exports"

    def test_cache_env_override(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv(CACHE_ENV_VAR, str(tmp_path / "cache"))
        assert default_cache_dir() == tmp_path / "cache"

    def test_data_env_override(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv(DATA_ENV_VAR, str(tmp_path / "data"))
        assert default_data_dir() == tmp_path / "data"
        assert default_model_dir() == tmp_path / "data" / "models"

    def test_temp_env_override(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv(TEMP_ENV_VAR, str(tmp_path))
        assert default_temp_dir() == tmp_path

    def test_empty_env_override_is_ignored(self, monkeypatch) -> None:
        monkeypatch.setenv(CACHE_ENV_VAR, "")
        assert "songlab" in str(default_cache_dir()).lower()


class TestHelpers:
    def test_ensure_directory_creates_parents(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c"
        assert ensure_directory(target) == target
        assert target.is_dir()

    def test_ensure_directory_is_idempotent(self, tmp_path: Path) -> None:
        ensure_directory(tmp_path)
        ensure_directory(tmp_path)
        assert tmp_path.is_dir()

    def test_relative_output_path_uses_base_dir(self, tmp_path: Path) -> None:
        resolved = resolve_output_path("out.json", base_dir=tmp_path)
        assert resolved == tmp_path / "out.json"

    def test_absolute_output_path_is_kept(self, tmp_path: Path) -> None:
        absolute = tmp_path / "out.json"
        assert resolve_output_path(absolute, base_dir=Path("/elsewhere")) == absolute

    def test_home_shortcut_is_expanded(self) -> None:
        assert "~" not in str(resolve_output_path("~/out.json"))
