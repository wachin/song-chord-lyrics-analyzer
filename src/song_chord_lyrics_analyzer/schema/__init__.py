"""Serialization of the canonical model.

The schema layer converts between the typed model and stable wire formats
(JSON first, other exporters later). It never defines musical semantics.
"""

from __future__ import annotations

from song_chord_lyrics_analyzer.schema.codec import (
    SCHEMA_VERSION,
    decode,
    encode,
    from_json,
    to_json,
)

__all__ = ["SCHEMA_VERSION", "decode", "encode", "from_json", "to_json"]
