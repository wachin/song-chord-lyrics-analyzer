"""Cross-platform path helpers (roadmap sections 4 and 104-105).

Nothing in the project may hard-code ``/tmp``, ``/home/user`` or
``C:\\Users\\...``. All platform-specific locations are resolved here.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

__all__ = [
    "default_cache_dir",
    "default_data_dir",
    "default_export_dir",
    "default_model_dir",
    "default_temp_dir",
    "ensure_directory",
    "is_windows",
    "is_macos",
    "is_linux",
    "resolve_output_path",
]

CACHE_ENV_VAR = "SONGLAB_CACHE_DIR"
DATA_ENV_VAR = "SONGLAB_DATA_DIR"
TEMP_ENV_VAR = "SONGLAB_TEMP_DIR"

_APP_DIR_NAME = "songlab"


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw).expanduser()


def _platform_cache_dir() -> Path:
    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / _APP_DIR_NAME / "Cache"
        return Path.home() / "AppData" / "Local" / _APP_DIR_NAME / "Cache"
    if is_macos():
        return Path.home() / "Library" / "Caches" / _APP_DIR_NAME
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    return root / _APP_DIR_NAME


def _platform_data_dir() -> Path:
    if is_windows():
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / _APP_DIR_NAME
        return Path.home() / "AppData" / "Roaming" / _APP_DIR_NAME
    if is_macos():
        return Path.home() / "Library" / "Application Support" / _APP_DIR_NAME
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / _APP_DIR_NAME


def default_cache_dir() -> Path:
    """Return the cache directory, honouring ``SONGLAB_CACHE_DIR``."""
    override = _env_path(CACHE_ENV_VAR)
    return override if override is not None else _platform_cache_dir()


def default_data_dir() -> Path:
    """Return the application data directory, honouring ``SONGLAB_DATA_DIR``."""
    override = _env_path(DATA_ENV_VAR)
    return override if override is not None else _platform_data_dir()


def default_model_dir() -> Path:
    """Return the directory where downloaded models are stored."""
    return default_data_dir() / "models"


def default_export_dir() -> Path:
    """Return the directory used when no explicit output directory is given."""
    return default_data_dir() / "exports"


def default_temp_dir() -> Path:
    """Return a writable temporary directory for the current platform.

    ``SONGLAB_TEMP_DIR`` overrides the system temporary directory.
    """
    override = _env_path(TEMP_ENV_VAR)
    if override is not None:
        return override
    return Path(tempfile.gettempdir())


def ensure_directory(path: Path) -> Path:
    """Create ``path`` (and parents) if needed and return it."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_output_path(path: str | Path, *, base_dir: Path | None = None) -> Path:
    """Resolve an output path without ever targeting an input file implicitly.

    Relative paths are resolved against ``base_dir`` (default: current working
    directory) so exports land where the user expects them.
    """
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = (base_dir or Path.cwd()) / candidate
    return candidate
