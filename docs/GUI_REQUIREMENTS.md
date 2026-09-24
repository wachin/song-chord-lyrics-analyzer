# GUI Requirements

**Status: not started — the analysis engine comes first (roadmap section 2).**

The GUI is a client of the analysis engine. It must never contain audio-analysis
algorithms and must never import `librosa`, `madmom`, `demucs`, `whisper` or any
other engine directly.

## Architecture constraint

```text
PyQt6 GUI
    ↓
Application services      (no Qt, no engines)
    ↓
Analysis pipeline → engine interfaces → concrete engines
```

## Planned modules (roadmap section 97)

```text
gui/
├── main_window.py
├── player.py
├── timeline.py
├── waveform.py
├── chord_editor.py
├── lyrics_editor.py
├── analysis_panel.py
├── engine_panel.py
├── settings_dialog.py
└── widgets/
```

## Planned capabilities

Transport: open audio, analyze, stop, play, pause, seek.

Workspace: waveform, timeline, lyrics, chords, beat grid, playback cursor
synchronised with audio position; clicking a chord or a lyric seeks to it.

Editing, all operating on the canonical model: edit lyrics, edit words, edit
chord labels, move/insert/delete/split/merge chords, transpose, simplify chords,
with undo/redo for every operation.

Confidence: shown as text (for example `Confidence: 82% — source: madmom`), never
by colour alone, so it stays accessible.

Engine comparison: an optional debug view listing the final chord next to each
engine's own answer, because disagreement is information.

Exports: the same exporters the CLI uses.

## Sequence

1. Phase 14 freezes the data model, engine interfaces, services, CLI terminology
   and exporters.
2. Phase 15 builds the GUI on top of that frozen surface.
3. Phase 16 stabilizes English menus, dialogs, shortcuts and errors.
4. Phase 17 adds Qt Linguist translations (see `INTERNATIONALIZATION.md`).
