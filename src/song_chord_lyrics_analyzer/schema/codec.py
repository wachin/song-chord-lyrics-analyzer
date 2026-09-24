"""Generic JSON codec for the canonical model (roadmap section 48).

``encode`` turns any canonical document into JSON-ready primitives and
``decode`` rebuilds typed objects from those primitives. A single codec avoids
hand-written ``to_dict``/``from_dict`` methods drifting apart.
"""

from __future__ import annotations

import json
import types
from dataclasses import MISSING, fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints

from song_chord_lyrics_analyzer.utils.errors import SchemaError
from song_chord_lyrics_analyzer.utils.logging import get_logger

__all__ = ["SCHEMA_VERSION", "decode", "encode", "from_json", "to_json"]

_logger = get_logger("schema.codec")

#: Version of the canonical JSON representation. Bump on breaking changes.
SCHEMA_VERSION = "1"

T = TypeVar("T")

_PRIMITIVES = (str, int, float, bool)
_SEQUENCE_ORIGINS = (list, set, frozenset, tuple)
_UNION_ORIGINS = (Union, types.UnionType)


def encode(value: Any) -> Any:
    """Convert a canonical value into JSON-serializable primitives.

    Supported inputs: dataclasses, ``Enum``, ``Path``, ``datetime``, lists,
    tuples, set-likes, mappings and primitives. Anything else raises
    :class:`SchemaError`, so unserializable state is detected immediately
    instead of silently disappearing from an export.
    """
    if value is None or isinstance(value, _PRIMITIVES):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple, set, frozenset)):
        return [encode(item) for item in value]
    if isinstance(value, dict):
        return {str(key): encode(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            descriptor.name: encode(getattr(value, descriptor.name)) for descriptor in fields(value)
        }
    raise SchemaError(
        f"Cannot encode value of type {type(value).__name__!r} to JSON.",
        hint=(
            "Only dataclasses, enums, paths, datetimes, lists, mappings and "
            "JSON primitives are supported."
        ),
    )


def _type_hints(cls: type) -> dict[str, Any]:
    try:
        return get_type_hints(cls)
    except NameError as exc:  # pragma: no cover - defensive
        raise SchemaError(f"Cannot resolve type hints for {cls.__name__}: {exc}") from exc


def _missing_required_fields(cls: type, data: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for descriptor in fields(cls):
        if descriptor.name in data:
            continue
        if descriptor.default is MISSING and descriptor.default_factory is MISSING:
            missing.append(descriptor.name)
    return missing


def decode(cls: type[T], data: Any) -> T:
    """Rebuild a canonical object of type ``cls`` from decoded JSON data."""
    result = _decode_type(cls, data)
    if result is None or not isinstance(result, cls):  # pragma: no cover - defensive
        raise SchemaError(f"Expected a JSON object for {cls.__name__}, got {type(data).__name__}.")
    return result


def _decode_dataclass(cls: type, data: Any) -> Any:
    if not isinstance(data, dict):
        raise SchemaError(f"Expected a JSON object for {cls.__name__}, got {type(data).__name__}.")
    missing = _missing_required_fields(cls, data)
    if missing:
        raise SchemaError(
            f"Missing required field(s) for {cls.__name__}: {', '.join(sorted(missing))}."
        )
    hints = _type_hints(cls)
    kwargs: dict[str, Any] = {}
    for descriptor in fields(cls):
        if descriptor.name not in data:
            continue
        field_type = hints.get(descriptor.name, Any)
        kwargs[descriptor.name] = _decode_type(field_type, data[descriptor.name])
    unknown = set(data) - {descriptor.name for descriptor in fields(cls)}
    if unknown:
        _logger.debug("ignoring unknown field(s) for %s: %s", cls.__name__, sorted(unknown))
    return cls(**kwargs)


def _decode_type(field_type: Any, data: Any) -> Any:
    if field_type is Any or field_type is object:
        return data
    if data is None:
        return None

    origin = get_origin(field_type)
    args = get_args(field_type)

    if origin in _UNION_ORIGINS:
        for candidate in (arg for arg in args if arg is not type(None)):
            try:
                return _decode_type(candidate, data)
            except (SchemaError, TypeError, ValueError):
                continue
        raise SchemaError(f"Cannot decode value {data!r} as {field_type}.")

    if origin in _SEQUENCE_ORIGINS:
        item_type = args[0] if args else Any
        if not isinstance(data, (list, tuple, set, frozenset)):
            raise SchemaError(f"Expected a JSON array, got {type(data).__name__}.")
        return [_decode_type(item_type, item) for item in data]

    if origin is dict or field_type is dict:
        value_type = args[1] if len(args) > 1 else Any
        if not isinstance(data, dict):
            raise SchemaError(f"Expected a JSON object, got {type(data).__name__}.")
        return {str(key): _decode_type(value_type, item) for key, item in data.items()}

    if isinstance(field_type, type):
        if issubclass(field_type, Enum):
            try:
                return field_type(data)
            except ValueError as exc:
                raise SchemaError(f"Unknown {field_type.__name__} value: {data!r}") from exc
        if issubclass(field_type, Path):
            return Path(data)
        if issubclass(field_type, datetime):
            try:
                return datetime.fromisoformat(data)
            except (ValueError, TypeError) as exc:
                raise SchemaError(f"Invalid ISO-8601 datetime: {data!r}") from exc
        if is_dataclass(field_type):
            return _decode_dataclass(field_type, data)

    return data


def to_json(value: Any, *, indent: int | None = 2, sort_keys: bool = False) -> str:
    """Encode a canonical document to a JSON string.

    The envelope carries the schema version so future readers can migrate old
    documents instead of failing silently.
    """
    payload = {"schema_version": SCHEMA_VERSION, "document": encode(value)}
    return json.dumps(payload, indent=indent, sort_keys=sort_keys, ensure_ascii=False)


def from_json(cls: type[T], text: str) -> T:
    """Decode a canonical document from a JSON string produced by :func:`to_json`."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaError(
            f"Invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"
        ) from exc
    if not isinstance(payload, dict) or "document" not in payload:
        raise SchemaError(
            "JSON payload is not a SongLab document.",
            hint="Expected an object with a top-level 'document' key.",
        )
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        _logger.warning(
            "document schema version %r differs from supported version %r",
            version,
            SCHEMA_VERSION,
        )
    return decode(cls, payload["document"])
