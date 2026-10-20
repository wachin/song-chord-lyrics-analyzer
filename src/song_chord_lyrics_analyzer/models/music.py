"""Canonical musical models (roadmap sections 12, 13, 32-35, 29-30 and 27).

A chord event preserves evidence, not just a label: root, quality, bass,
extensions, confidence and origin. Ambiguous evidence stays ambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.models.confidence import ConfidenceScore

__all__ = [
    "BarEvent",
    "BeatEvent",
    "CHORD_QUALITY_SUFFIX",
    "ChordEvent",
    "ChordQuality",
    "DownbeatEvent",
    "KeyEstimate",
    "KeyMode",
    "NOTE_NAME_TO_PITCH_CLASS",
    "NoteEvent",
    "PITCH_CLASS_NAMES",
    "Stem",
    "StemName",
    "TempoEstimate",
]

#: Canonical (sharp-spelled) pitch class names, indexed by pitch class number.
PITCH_CLASS_NAMES: tuple[str, ...] = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)

#: Accepted note spellings. Flat and sharp aliases normalise to canonical names.
NOTE_NAME_TO_PITCH_CLASS: dict[str, int] = {
    name: index for index, name in enumerate(PITCH_CLASS_NAMES)
}
NOTE_NAME_TO_PITCH_CLASS.update(
    {
        "Cb": 11,
        "Db": 1,
        "Eb": 3,
        "Fb": 4,
        "Gb": 6,
        "Ab": 8,
        "Bb": 10,
        "E#": 5,
        "B#": 0,
        "Dbb": 0,
    }
)


class ChordQuality(str, Enum):
    """Chord vocabulary, expanded phase by phase (roadmap section 13).

    ``NO_CHORD`` is the explicit ``N`` marker. ``UNKNOWN`` and ``OTHER`` keep
    the engine's raw label intact instead of inventing a precise quality.
    """

    # Phase 1 - conservative vocabulary.
    MAJOR = "major"
    MINOR = "minor"
    NO_CHORD = "no_chord"
    # Phase 2.
    DOMINANT7 = "7"
    MAJOR7 = "maj7"
    MINOR7 = "m7"
    SUS2 = "sus2"
    SUS4 = "sus4"
    DIMINISHED = "dim"
    AUGMENTED = "aug"
    # Phase 3.
    ADD9 = "add9"
    SIXTH = "6"
    MINOR_SIXTH = "m6"
    NINTH = "9"
    MINOR_NINTH = "m9"
    # Fallbacks.
    OTHER = "other"
    UNKNOWN = "unknown"


#: Canonical suffix used when rendering a chord label from its parts.
CHORD_QUALITY_SUFFIX: dict[ChordQuality, str] = {
    ChordQuality.MAJOR: "",
    ChordQuality.MINOR: "m",
    ChordQuality.NO_CHORD: "N",
    ChordQuality.DOMINANT7: "7",
    ChordQuality.MAJOR7: "maj7",
    ChordQuality.MINOR7: "m7",
    ChordQuality.SUS2: "sus2",
    ChordQuality.SUS4: "sus4",
    ChordQuality.DIMINISHED: "dim",
    ChordQuality.AUGMENTED: "aug",
    ChordQuality.ADD9: "add9",
    ChordQuality.SIXTH: "6",
    ChordQuality.MINOR_SIXTH: "m6",
    ChordQuality.NINTH: "9",
    ChordQuality.MINOR_NINTH: "m9",
    ChordQuality.OTHER: "",
    ChordQuality.UNKNOWN: "",
}


def _validate_optional_time(value: float | None, label: str) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{label} must not be negative, got {value!r}")


def _validate_interval(start: float, end: float | None, label: str) -> None:
    if end is not None and end < start:
        raise ValueError(f"{label} end ({end!r}) must not precede start ({start!r})")


@dataclass
class ChordEvent:
    """One chord observation on the timeline.

    Attributes:
        start: Start time in seconds.
        end: End time in seconds, when the engine provides one.
        root: Root pitch class name (``"C"``, ``"F#"``), ``None`` for silence.
        quality: Interpreted chord quality.
        bass: Bass pitch class for slash chords (``"C/E"`` -> ``"E"``).
        extensions: Additional computed intervals or tensions, unmodified.
        label: Rendered label. Always populated so the raw text survives.
        confidence: Confidence reported by the engine.
        source: Engine or module that produced the event.
        metadata: Engine-specific evidence, kept verbatim.
    """

    start: float
    end: float | None = None
    root: str | None = None
    quality: ChordQuality = ChordQuality.UNKNOWN
    bass: str | None = None
    extensions: list[str] = field(default_factory=list)
    label: str = ""
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore.unknown)
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_optional_time(self.start, "chord start")
        _validate_interval(self.start, self.end, "chord")
        if self.root is not None and self.root not in NOTE_NAME_TO_PITCH_CLASS:
            raise ValueError(f"unknown root note: {self.root!r}")
        if self.bass is not None and self.bass not in NOTE_NAME_TO_PITCH_CLASS:
            raise ValueError(f"unknown bass note: {self.bass!r}")
        if not self.label:
            self.label = self.to_label()

    @classmethod
    def silence(
        cls,
        start: float,
        end: float | None = None,
        *,
        source: str | None = None,
        confidence: ConfidenceScore | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChordEvent:
        """Build an explicit "no chord" (``N``) event.

        ``confidence`` and ``metadata`` are forwarded unchanged: a claim of
        silence has evidence behind it too, and it must not lose it merely
        because the label is ``N``.
        """
        return cls(
            start=start,
            end=end,
            quality=ChordQuality.NO_CHORD,
            label="N",
            confidence=confidence or ConfidenceScore.unknown(),
            source=source,
            metadata=dict(metadata or {}),
        )

    @property
    def duration(self) -> float | None:
        """Chord duration in seconds when both boundaries are known."""
        if self.end is None:
            return None
        return self.end - self.start

    @property
    def is_silence(self) -> bool:
        """Whether the event marks "no chord"."""
        return self.quality is ChordQuality.NO_CHORD

    def to_label(self) -> str:
        """Render a label from the structured parts.

        ``N`` means "no chord is playing". An event without any evidence renders
        as ``?`` instead, so uncertainty is never reported as silence.
        """
        if self.quality is ChordQuality.NO_CHORD:
            return "N"
        if self.root is None:
            return "?"
        suffix = CHORD_QUALITY_SUFFIX.get(self.quality, "")
        label = f"{self.root}{suffix}"
        if self.bass is not None and self.bass != self.root:
            label = f"{label}/{self.bass}"
        return label


@dataclass
class BeatEvent:
    """A detected beat."""

    time: float
    index: int | None = None
    position_in_bar: int | None = None
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore.unknown)
    source: str | None = None

    def __post_init__(self) -> None:
        _validate_optional_time(self.time, "beat time")
        if self.position_in_bar is not None and self.position_in_bar < 1:
            raise ValueError(f"beat position_in_bar is 1-based, got {self.position_in_bar!r}")


@dataclass
class DownbeatEvent:
    """A detected downbeat, i.e. the first beat of a bar."""

    time: float
    bar_index: int | None = None
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore.unknown)
    source: str | None = None

    def __post_init__(self) -> None:
        _validate_optional_time(self.time, "downbeat time")


@dataclass
class BarEvent:
    """A metrical bar."""

    index: int
    start: float
    end: float | None = None
    beats: int | None = None
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore.unknown)
    source: str | None = None

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError(f"bar index must not be negative, got {self.index!r}")
        _validate_optional_time(self.start, "bar start")
        _validate_interval(self.start, self.end, "bar")

    @property
    def is_complete(self) -> bool:
        """Whether the bar has a closing boundary."""
        return self.end is not None


class KeyMode(str, Enum):
    """Musical mode of a key estimate."""

    MAJOR = "major"
    MINOR = "minor"
    UNKNOWN = "unknown"


@dataclass
class KeyEstimate:
    """Detected key (roadmap section 32)."""

    tonic: str | None = None
    mode: KeyMode = KeyMode.UNKNOWN
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore.unknown)
    source: str | None = None

    def __post_init__(self) -> None:
        if self.tonic is not None and self.tonic not in NOTE_NAME_TO_PITCH_CLASS:
            raise ValueError(f"unknown tonic: {self.tonic!r}")

    @property
    def label(self) -> str:
        """Human-readable key, for example ``"C major"``."""
        if self.tonic is None or self.mode is KeyMode.UNKNOWN:
            return "unknown"
        return f"{self.tonic} {self.mode.value}"


@dataclass
class TempoEstimate:
    """Detected tempo (roadmap section 33).

    Half-time and double-time ambiguity is recorded instead of silently
    normalised: :attr:`alternatives` keeps the competing interpretations.
    """

    bpm: float
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore.unknown)
    source: str | None = None
    meter: str | None = None
    alternatives: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.bpm <= 0:
            raise ValueError(f"bpm must be positive, got {self.bpm!r}")

    @property
    def is_ambiguous(self) -> bool:
        """Whether competing tempo interpretations were reported."""
        return bool(self.alternatives)


@dataclass
class NoteEvent:
    """A single transcribed note (roadmap sections 29 and 30)."""

    start: float
    end: float | None = None
    pitch_midi: int | None = None
    velocity: int | None = None
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore.unknown)
    source: str | None = None
    instrument: str | None = None

    def __post_init__(self) -> None:
        _validate_optional_time(self.start, "note start")
        _validate_interval(self.start, self.end, "note")
        if self.pitch_midi is not None and not 0 <= self.pitch_midi <= 127:
            raise ValueError(f"pitch_midi must be within [0, 127], got {self.pitch_midi!r}")
        if self.velocity is not None and not 0 <= self.velocity <= 127:
            raise ValueError(f"velocity must be within [0, 127], got {self.velocity!r}")


class StemName(str, Enum):
    """Standard stem names produced by source separation (roadmap section 27)."""

    VOCALS = "vocals"
    DRUMS = "drums"
    BASS = "bass"
    OTHER = "other"
    PIANO = "piano"
    GUITAR = "guitar"


@dataclass
class Stem:
    """A separated audio stem and how it was produced."""

    name: StemName
    path: Path | None = None
    source: str | None = None
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore.unknown)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.path is not None:
            self.path = Path(self.path)
