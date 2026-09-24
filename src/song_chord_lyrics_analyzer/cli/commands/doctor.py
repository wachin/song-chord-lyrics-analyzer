"""``songlab doctor`` - report environment and dependency status.

Diagnostics come before analysis: this command tells the user which optional
tools are actually usable, where caches live and which engines are registered.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

import song_chord_lyrics_analyzer
from song_chord_lyrics_analyzer import __version__
from song_chord_lyrics_analyzer.audio.ffmpeg import (
    discover_ffmpeg_tools,
    ffmpeg_install_hint,
    tool_version,
)
from song_chord_lyrics_analyzer.engines import EngineKind, create_default_registry
from song_chord_lyrics_analyzer.utils.paths import (
    default_cache_dir,
    default_data_dir,
    default_export_dir,
    default_model_dir,
    default_temp_dir,
)

__all__ = ["add_arguments", "collect_status", "format_report", "run"]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register ``songlab doctor`` arguments."""
    parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable JSON instead of a report",
    )


def _package_path() -> str | None:
    """Return the directory the package is loaded from (``None`` if frozen)."""
    module_file = getattr(song_chord_lyrics_analyzer, "__file__", None)
    if not module_file:
        return None
    return str(Path(module_file).parent)


def _tool_status(name: str, path: Any) -> dict[str, Any]:
    if path is None:
        return {"name": name, "found": False, "path": None, "version": None}
    return {"name": name, "found": True, "path": str(path), "version": tool_version(path)}


def collect_status() -> dict[str, Any]:
    """Collect environment, dependency and registry status."""
    tools = discover_ffmpeg_tools()
    registry = create_default_registry()

    return {
        "application": {
            "name": "song-chord-lyrics-analyzer",
            "version": __version__,
            "cli": "songlab",
            "package_path": _package_path(),
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "tools": {
            "ffmpeg": _tool_status("ffmpeg", tools.ffmpeg),
            "ffprobe": _tool_status("ffprobe", tools.ffprobe),
        },
        "directories": {
            "cache": str(default_cache_dir()),
            "data": str(default_data_dir()),
            "models": str(default_model_dir()),
            "exports": str(default_export_dir()),
            "temp": str(default_temp_dir()),
        },
        "engines": {
            kind.value: registry.names(kind) for kind in EngineKind if registry.names(kind)
        },
    }


def format_report(status: dict[str, Any]) -> str:
    """Render the collected status as a readable report."""
    application = status["application"]
    lines = [
        "SongLab doctor",
        "==============",
        f"Application:  {application['name']} {application['version']}",
        f"Package path: {application['package_path']}",
        f"Python:       {status['python']['version']} ({status['python']['implementation']})",
        f"Interpreter:  {status['python']['executable']}",
        f"Platform:     {status['platform']['system']} {status['platform']['release']} "
        f"({status['platform']['machine']})",
        "",
        "External tools",
    ]

    for name in ("ffmpeg", "ffprobe"):
        tool = status["tools"][name]
        if tool["found"]:
            lines.append(f"  {name:<8} ok      {tool['path']}")
            if tool["version"]:
                lines.append(f"           {tool['version']}")
        else:
            lines.append(f"  {name:<8} missing")

    if not all(status["tools"][name]["found"] for name in ("ffmpeg", "ffprobe")):
        lines.append("")
        lines.extend(f"  {line}" for line in ffmpeg_install_hint().splitlines())

    lines.append("")
    lines.append("Directories")
    for label in ("cache", "data", "models", "exports", "temp"):
        lines.append(f"  {label:<8} {status['directories'][label]}")

    lines.append("")
    lines.append("Analysis engines")
    if status["engines"]:
        for kind, names in sorted(status["engines"].items()):
            lines.append(f"  {kind:<8} {', '.join(names)}")
    else:
        lines.append("  none registered yet (engines are added in later roadmap phases)")

    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    """Execute ``songlab doctor``."""
    status = collect_status()
    if args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        print(format_report(status))
    return 0
