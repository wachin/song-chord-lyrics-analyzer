"""Alignment stage (roadmap sections 36, 37 and 91) - not implemented yet.

Planned responsibility: place lyrics, chords, beats, downbeats and bars on one
shared timeline, keeping the canonical timeline free to contain overlapping
semantic events (a word may span a chord change; a line may hold several
chords).

The public entry point will be ``align_events(...) -> AlignmentResult`` and the
:class:`~song_chord_lyrics_analyzer.models.analysis.AlignmentResult` model
already exists to receive its output.
"""

from __future__ import annotations

__all__: list[str] = []
