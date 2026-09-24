"""Export stage (roadmap sections 48-51 and 94) - not implemented yet.

Planned responsibility: render the canonical model to JSON, CSV, TXT,
ChordPro, Markdown, MIDI and MusicXML. Exporters are pure functions of the
canonical document plus explicit output paths; the model never becomes
Markdown or ChordPro.

JSON scaffolding already exists in
:mod:`song_chord_lyrics_analyzer.schema.codec`; the chord/lyric renderers land
in phase 12.
"""

from __future__ import annotations

__all__: list[str] = []
