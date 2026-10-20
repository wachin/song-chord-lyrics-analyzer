"""Confidence representation (roadmap section 39).

Every inference keeps the confidence reported by its source. Uncertainty is
never silently converted into an exact musical fact, and ``unknown`` is kept
distinct from ``0.0``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = ["ConfidenceLevel", "ConfidenceScore", "level_for_value"]


class ConfidenceLevel(str, Enum):
    """Coarse, human-readable banding of a confidence value."""

    UNKNOWN = "unknown"
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


def level_for_value(value: float) -> ConfidenceLevel:
    """Map a numeric confidence in ``[0.0, 1.0]`` to a :class:`ConfidenceLevel`."""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"confidence value must be within [0.0, 1.0], got {value!r}")
    if value < 0.2:
        return ConfidenceLevel.VERY_LOW
    if value < 0.4:
        return ConfidenceLevel.LOW
    if value < 0.6:
        return ConfidenceLevel.MEDIUM
    if value < 0.8:
        return ConfidenceLevel.HIGH
    return ConfidenceLevel.VERY_HIGH


@dataclass(frozen=True)
class ConfidenceScore:
    """A confidence value together with its band and origin.

    Attributes:
        value: Numeric confidence in ``[0.0, 1.0]`` or ``None`` when the source
            does not provide one. ``None`` must not be read as "zero".
        level: Coarse band, derived automatically whenever ``value`` is known.
        source: Optional origin label (engine name, heuristic name, ...).
    """

    value: float | None = None
    level: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    source: str | None = None

    def __post_init__(self) -> None:
        if self.value is not None:
            derived = level_for_value(self.value)
            object.__setattr__(self, "level", derived)
        elif not isinstance(self.level, ConfidenceLevel):  # pragma: no cover - defensive
            object.__setattr__(self, "level", ConfidenceLevel(self.level))

    @classmethod
    def from_value(cls, value: float | None, source: str | None = None) -> ConfidenceScore:
        """Build a score from a numeric value (or ``None``)."""
        if value is None:
            return cls.unknown(source)
        return cls(value=value, source=source)

    @classmethod
    def unknown(cls, source: str | None = None) -> ConfidenceScore:
        """Build an explicitly unknown score."""
        return cls(value=None, level=ConfidenceLevel.UNKNOWN, source=source)

    @property
    def is_known(self) -> bool:
        """Whether the source actually reported a numeric confidence."""
        return self.value is not None

    def __str__(self) -> str:
        if self.value is None:
            return "unknown"
        return f"{self.value:.2f} ({self.level.value})"
