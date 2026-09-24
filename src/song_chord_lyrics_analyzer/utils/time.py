"""Timestamp helpers shared by the CLI and by exporters.

All timestamps inside the canonical model are seconds as ``float``; formatting
for humans happens only at the edges.
"""

from __future__ import annotations

__all__ = ["format_timestamp", "format_duration", "parse_timestamp"]


def format_timestamp(seconds: float | None) -> str:
    """Format seconds as ``HH:MM:SS.mmm`` (``"unknown"`` for ``None``).

    Negative values are rejected because they would indicate a broken timeline.
    """
    if seconds is None:
        return "unknown"
    if seconds < 0:
        raise ValueError(f"timestamp must not be negative, got {seconds!r}")
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{millis:03d}"


def format_duration(seconds: float | None) -> str:
    """Format seconds as ``M:SS`` for compact display (``"unknown"`` for ``None``)."""
    if seconds is None:
        return "unknown"
    if seconds < 0:
        raise ValueError(f"duration must not be negative, got {seconds!r}")
    total = round(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_timestamp(text: str) -> float:
    """Parse ``SS``, ``MM:SS`` or ``HH:MM:SS(.mmm)`` into seconds.

    Raises:
        ValueError: When the text is not a valid timestamp.
    """
    raw = text.strip()
    if not raw:
        raise ValueError("empty timestamp")
    parts = raw.split(":")
    if len(parts) > 3:
        raise ValueError(f"invalid timestamp: {text!r}")
    total = 0.0
    for part in parts:
        if not part:
            raise ValueError(f"invalid timestamp: {text!r}")
        total = total * 60.0 + float(part)
    if total < 0:
        raise ValueError(f"timestamp must not be negative: {text!r}")
    return total
