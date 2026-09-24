"""``songlab info`` - inspect audio metadata (roadmap section 84).

The command reports technical facts first and untrusted descriptive tags
afterwards, so the two are never confused.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.audio.probe import compute_file_hash, probe_audio
from song_chord_lyrics_analyzer.models.audio import AudioDocument
from song_chord_lyrics_analyzer.schema.codec import encode

__all__ = ["add_arguments", "format_bytes", "format_report", "run"]

_TAG_ORDER = ("title", "artist", "album", "genre", "year")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register ``songlab info`` arguments."""
    parser.add_argument("audio", type=Path, help="audio file to inspect")
    parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable JSON instead of a report",
    )
    parser.add_argument(
        "--hash",
        action="store_true",
        help="also print the SHA-256 digest of the file (used for caching and provenance)",
    )


def format_bytes(size: int | None) -> str:
    """Format a byte count using binary units."""
    if size is None:
        return "unknown"
    if size < 1024:
        return f"{size} B"
    value = size / 1024
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"  # pragma: no cover - unreachable


def _format_optional(value: Any, suffix: str = "") -> str:
    if value is None:
        return "unknown"
    return f"{value}{suffix}"


def format_report(document: AudioDocument, *, file_hash: str | None = None) -> str:
    """Render a human-readable metadata report."""
    lines = [
        f"File:        {document.path}",
        f"Format:      {_format_optional(document.format)}",
        f"Codec:       {_format_optional(document.codec)}",
        f"Duration:    {document.duration_label}"
        + (f" ({document.duration:.3f} s)" if document.duration is not None else ""),
        f"Sample rate: {_format_optional(document.sample_rate, ' Hz')}",
        f"Channels:    {document.channels_label}",
        f"Bit depth:   {_format_optional(document.bit_depth, ' bit')}",
        "Bitrate:     "
        + (
            f"{document.bitrate_kbps:.0f} kbit/s"
            if document.bitrate_kbps is not None
            else "unknown"
        ),
        f"File size:   {format_bytes(document.file_size)}",
        f"Probed with: {_format_optional(document.probe_backend)}",
    ]

    if file_hash:
        lines.append(f"SHA-256:     {file_hash}")

    present_tags = [
        (field, getattr(document, field)) for field in _TAG_ORDER if getattr(document, field)
    ]
    if present_tags or document.extra_tags:
        lines.append("")
        lines.append("Tags (informational, never trusted):")
        for field, value in present_tags:
            lines.append(f"  {field:<12} {value}")
        for key in sorted(document.extra_tags):
            lines.append(f"  {key:<12} {document.extra_tags[key]}")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    """Execute ``songlab info``."""
    document = probe_audio(args.audio)
    file_hash = compute_file_hash(document.path) if args.hash else None

    if args.json:
        payload = encode(document)
        payload["sha256"] = file_hash
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(format_report(document, file_hash=file_hash))
    return 0
