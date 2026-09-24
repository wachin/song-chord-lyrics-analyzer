"""Unit tests for the engine registry (roadmap sections 58 and 59)."""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.engines import (
    EngineKind,
    EngineRegistry,
    create_default_registry,
)
from song_chord_lyrics_analyzer.models import EngineInfo
from song_chord_lyrics_analyzer.utils.errors import DuplicateEngineError, EngineNotFoundError


class TestRegistration:
    def test_engine_is_registered_under_its_kind(self, fake_engine: type) -> None:
        registry = EngineRegistry()
        registry.register(fake_engine("baseline"))
        assert registry.names(EngineKind.CHORDS) == ["baseline"]
        assert registry.get(EngineKind.CHORDS, "baseline").name == "baseline"

    def test_explicit_kind_is_honoured(self, fake_engine: type) -> None:
        registry = EngineRegistry()
        registry.register(fake_engine("whisper", EngineKind.LYRICS), EngineKind.LYRICS)
        assert registry.names(EngineKind.LYRICS) == ["whisper"]

    def test_engine_kind_mismatch_is_rejected(self, fake_engine: type) -> None:
        registry = EngineRegistry()
        with pytest.raises(ValueError, match="reports kind"):
            registry.register(fake_engine("whisper", EngineKind.CHORDS), EngineKind.LYRICS)

    def test_duplicate_registration_is_rejected(self, fake_engine: type) -> None:
        registry = EngineRegistry()
        registry.register(fake_engine("baseline"))
        with pytest.raises(DuplicateEngineError):
            registry.register(fake_engine("baseline"))

    def test_engine_without_kind_needs_explicit_kind(self) -> None:
        class NoKind:
            name = "no-kind"

            def is_available(self) -> bool:
                return True

            def engine_info(self) -> EngineInfo:
                return EngineInfo(name=self.name, kind="chords")

        registry = EngineRegistry()
        with pytest.raises(ValueError, match="kind"):
            registry.register(NoKind())

    def test_engine_without_name_is_rejected(self, fake_engine: type) -> None:
        registry = EngineRegistry()
        with pytest.raises(ValueError, match="name"):
            registry.register(fake_engine(""))

    def test_engine_without_engine_info_is_rejected(self) -> None:
        class NoInfo:
            name = "no-info"
            kind = "chords"

            def is_available(self) -> bool:
                return True

        registry = EngineRegistry()
        with pytest.raises(ValueError, match="engine_info"):
            registry.register(NoInfo())

    def test_minimal_engines_are_accepted(self) -> None:
        class FunctionalEngine:
            name = "functional"
            kind = "chords"

            def is_available(self) -> bool:
                return True

            def engine_info(self) -> EngineInfo:
                return EngineInfo(name=self.name, kind=self.kind)

        registry = EngineRegistry()
        registry.register(FunctionalEngine())
        assert registry.available(EngineKind.CHORDS) == ["functional"]


class TestLookup:
    def test_unknown_engine_lists_available_ones(self, fake_engine: type) -> None:
        registry = EngineRegistry()
        registry.register(fake_engine("baseline"))
        registry.register(fake_engine("madmom"))
        with pytest.raises(EngineNotFoundError) as excinfo:
            registry.get(EngineKind.CHORDS, "pitchperfect")
        assert excinfo.value.available == ["baseline", "madmom"]
        assert "pitchperfect" in str(excinfo.value)

    def test_find_searches_every_kind(self, fake_engine: type) -> None:
        registry = EngineRegistry()
        registry.register(fake_engine("whisper", EngineKind.LYRICS))
        assert registry.find("whisper").name == "whisper"

    def test_find_raises_for_unknown_engine(self) -> None:
        registry = EngineRegistry()
        with pytest.raises(EngineNotFoundError):
            registry.find("nope")

    def test_availability_is_reported_per_engine(self, fake_engine: type) -> None:
        registry = EngineRegistry()
        registry.register(fake_engine("available", available=True))
        registry.register(fake_engine("unavailable", available=False))
        assert registry.names(EngineKind.CHORDS) == ["available", "unavailable"]
        assert registry.available(EngineKind.CHORDS) == ["available"]

    def test_broken_availability_does_not_crash_the_registry(self, fake_engine: type) -> None:
        class Broken(fake_engine):  # type: ignore[misc,valid-type]
            def is_available(self) -> bool:
                raise RuntimeError("boom")

        registry = EngineRegistry()
        registry.register(Broken("broken"))
        assert registry.available(EngineKind.CHORDS) == []

    def test_contains_and_len(self, fake_engine: type) -> None:
        registry = EngineRegistry()
        registry.register(fake_engine("baseline"))
        assert "baseline" in registry
        assert "missing" not in registry
        assert len(registry) == 1

    def test_unregister_and_clear(self, fake_engine: type) -> None:
        registry = EngineRegistry()
        registry.register(fake_engine("baseline"))
        registry.unregister(EngineKind.CHORDS, "baseline")
        assert len(registry) == 0
        registry.register(fake_engine("madmom"))
        registry.clear()
        assert len(registry) == 0


class TestProvenance:
    def test_engine_infos_collects_every_engine(self, fake_engine: type) -> None:
        registry = EngineRegistry()
        registry.register(fake_engine("baseline", version="1.2.3"))
        registry.register(fake_engine("whisper", EngineKind.LYRICS))
        infos = registry.engine_infos()
        assert {info.name for info in infos} == {"baseline", "whisper"}
        assert next(info for info in infos if info.name == "baseline").version == "1.2.3"

    def test_broken_engine_info_is_tolerated(self, fake_engine: type) -> None:
        class Broken(fake_engine):  # type: ignore[misc,valid-type]
            def engine_info(self):  # type: ignore[no-untyped-def]
                raise RuntimeError("boom")

        registry = EngineRegistry()
        registry.register(Broken("broken"))
        infos = registry.engine_infos()
        assert [info.name for info in infos] == ["broken"]
        assert infos[0].version is None


class TestDefaultRegistry:
    def test_registry_is_creation_ready_but_empty_in_phase_zero(self) -> None:
        registry = create_default_registry()
        assert isinstance(registry, EngineRegistry)
        assert registry.all_names() == []
        assert registry.kinds() == list(EngineKind)
