"""Engine registry (roadmap sections 58 and 59).

Engines register themselves by kind and name so the CLI can select one without
knowing any implementation detail::

    songlab chords song.mp3 --engine madmom

Adding an engine requires an adapter, a configuration entry, tests and
documentation - never a change to the CLI or the GUI.
"""

from __future__ import annotations

from typing import Any

from song_chord_lyrics_analyzer.engines.base import EngineKind
from song_chord_lyrics_analyzer.models.analysis import EngineInfo
from song_chord_lyrics_analyzer.utils.errors import DuplicateEngineError, EngineNotFoundError
from song_chord_lyrics_analyzer.utils.logging import get_logger

__all__ = ["EngineRegistry", "create_default_registry"]

_logger = get_logger("engines.registry")


def _validate_engine(engine: Any, kind: EngineKind) -> str:
    """Validate the minimal engine contract and return its name.

    Duck typing is used on purpose: requiring ``isinstance`` against a runtime
    protocol would reject perfectly valid adapters and complicate testing.
    """
    name = getattr(engine, "name", None)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("engine.name must be a non-empty string")
    engine_kind = getattr(engine, "kind", None)
    if engine_kind is not None and EngineKind(engine_kind) is not kind:
        raise ValueError(
            f"engine {name!r} reports kind {EngineKind(engine_kind).value!r}, not {kind.value!r}"
        )
    if not callable(getattr(engine, "is_available", None)):
        raise ValueError(f"engine {name!r} must implement is_available()")
    if not callable(getattr(engine, "engine_info", None)):
        raise ValueError(f"engine {name!r} must implement engine_info()")
    return name.strip()


class EngineRegistry:
    """A registry of optional analysis engines, grouped by kind."""

    def __init__(self) -> None:
        self._engines: dict[EngineKind, dict[str, Any]] = {kind: {} for kind in EngineKind}

    def register(self, engine: Any, kind: EngineKind | str | None = None) -> None:
        """Register ``engine`` for the given kind.

        Args:
            engine: The engine adapter. Must expose ``name``, ``is_available``
                and ``engine_info``.
            kind: Explicit kind. Defaults to the engine's ``kind`` attribute.

        Raises:
            ValueError: When the engine contract is not satisfied.
            DuplicateEngineError: When the name is already taken for that kind.
        """
        resolved_kind = EngineKind(kind) if kind is not None else getattr(engine, "kind", None)
        if resolved_kind is None:
            raise ValueError("register() needs an explicit kind or an engine.kind attribute")
        resolved_kind = EngineKind(resolved_kind)
        name = _validate_engine(engine, resolved_kind)
        bucket = self._engines[resolved_kind]
        if name in bucket:
            raise DuplicateEngineError(resolved_kind.value, name)
        bucket[name] = engine
        _logger.debug("registered %s engine %r", resolved_kind.value, name)

    def unregister(self, kind: EngineKind | str, name: str) -> None:
        """Remove a previously registered engine, if present."""
        self._engines[EngineKind(kind)].pop(name, None)

    def clear(self) -> None:
        """Remove every registered engine (mainly useful in tests)."""
        for bucket in self._engines.values():
            bucket.clear()

    def names(self, kind: EngineKind | str) -> list[str]:
        """Return the registered engine names for ``kind``, sorted."""
        return sorted(self._engines[EngineKind(kind)])

    def kinds(self) -> list[EngineKind]:
        """Return every supported engine kind."""
        return list(EngineKind)

    def get(self, kind: EngineKind | str, name: str) -> Any:
        """Return a registered engine.

        Raises:
            EngineNotFoundError: When no engine with that name is registered.
        """
        resolved_kind = EngineKind(kind)
        bucket = self._engines[resolved_kind]
        engine = bucket.get(name)
        if engine is None:
            raise EngineNotFoundError(resolved_kind.value, name, sorted(bucket))
        return engine

    def find(self, name: str, kind: EngineKind | str | None = None) -> Any:
        """Return the engine called ``name``, searching every kind when needed."""
        if kind is not None:
            return self.get(kind, name)
        matches = [
            engine
            for bucket in self._engines.values()
            for key, engine in bucket.items()
            if key == name
        ]
        if not matches:
            raise EngineNotFoundError("analysis", name, self.all_names())
        return matches[0]

    def available(self, kind: EngineKind | str) -> list[str]:
        """Return names of engines that report being usable right now."""
        result: list[str] = []
        for name, engine in sorted(self._engines[EngineKind(kind)].items()):
            try:
                if engine.is_available():
                    result.append(name)
            except Exception as exc:  # availability must never crash the CLI
                _logger.warning("could not check availability of %r: %s", name, exc)
        return result

    def all_names(self) -> list[str]:
        """Return every registered engine name across all kinds."""
        names = {name for bucket in self._engines.values() for name in bucket}
        return sorted(names)

    def engine_infos(self) -> list[EngineInfo]:
        """Return provenance metadata for every registered engine."""
        infos: list[EngineInfo] = []
        for kind, bucket in self._engines.items():
            for name, engine in sorted(bucket.items()):
                try:
                    info = engine.engine_info()
                except Exception as exc:  # metadata must be best-effort
                    _logger.warning("could not read info of %r: %s", name, exc)
                    info = EngineInfo(name=name, kind=kind.value)
                infos.append(info)
        return infos

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and any(name in bucket for bucket in self._engines.values())

    def __len__(self) -> int:
        return sum(len(bucket) for bucket in self._engines.values())

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"EngineRegistry({len(self)} engines: {', '.join(self.all_names()) or 'none'})"


def create_default_registry() -> EngineRegistry:
    """Create the registry used by the CLI.

    Concrete engines are registered here as their roadmap phases land: the
    chroma baseline (phase 4), Chordino/Sonic Annotator, Madmom, PitchPerfect,
    Faster-Whisper and Demucs. Keeping this function explicit means the CLI and
    the future GUI see exactly one place where engines become available.
    """
    registry = EngineRegistry()
    return registry
