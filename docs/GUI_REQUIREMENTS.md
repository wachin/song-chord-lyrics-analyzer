# GUI Requirements

**Status: the minimal window exists (roadmap Phase D, 2026-10-08); the rest of
this document is still a plan.**

`songlab gui` opens it: open an audio file, see its waveform timeline with the
detected chords, play/pause/stop, seek by clicking or dragging the timeline (or
with the arrow keys), and always see the chord for the current position next to
the track time and the analysis summary (key, tempo, engines, provenance).

Everything else described below - lyrics, editing, transpose, simplification,
export dialogs, confidence panels, translations - is `[F]` work that has not been
started. The window is laid out for it, but no widget claims it yet.

## What exists today

```text
src/song_chord_lyrics_analyzer/gui/
├── __init__.py          require_qt() + run(): Qt is imported lazily, so a
│                        Qt-free install keeps every other command working
├── main_window.py       MainWindow + launch(): transport, chord/time/state
│                        labels, one refresh per timer tick, file dialog
├── timeline.py          TimelineWidget: waveform, chord strip, playhead,
│                        seek_requested signal (click or drag)
└── analysis_panel.py    AnalysisPanel: the rows summarize() produced
```

The data all comes from the application layer, which is also where the logic and
the tests live:

* `SongSession` (`app/session.py`) owns the song, the player and
  `chord_at(seconds)`, and reduces the decoded samples to waveform peaks
  (`waveform_peaks(buckets)`, cached per resolution).
* `app/display.py` turns a `SessionSnapshot` into the `DisplayFrame` the window
  draws - the same frame `songlab play` prints as a line of text.
* `app/timeline.py` turns the chord events into bands in seconds and maps
  seconds to pixels and back, which is what makes a click a seek.
* `app/summary.py` turns the document plus the run steps into the panel rows.

There is deliberately **no** `gui/player.py` and no `gui/waveform.py`: the window
drives the session's existing `SoundDevicePlayer` (no second audio path, and a
Qt Multimedia backend can still implement the same `Player` protocol later), and
one widget paints the waveform, the chord strip and the playhead together so they
cannot disagree about where a second is.

The GUI is a client of the application layer. It must never contain
audio-analysis or synchronization algorithms and must never import `librosa`,
`madmom`, `demucs`, `whisper`, `numpy`, `analysis/` internals or any other engine
directly.

## Architecture constraint

```text
PyQt6 GUI             (thin widgets)
    ↓
app/ session + presenters   (SongSession, DisplayFrame, ChordBand, SummaryRow —
                             no Qt, no engines)
    ↓
Analysis pipeline → engine interfaces → concrete engines
```

## Testing constraint

The logic stays in plain-Python presenters so the window can be tested without a
display: the Qt dependency is an optional `gui` extra, the core install and the
test matrix stay Qt-free, and the window's own tests set
`QT_QPA_PLATFORM=offscreen`, where `paintEvent` and `render()` run into memory.

What is tested:

* the presenters (`tests/unit/test_timeline_presenter.py`,
  `test_summary_presenter.py`, `test_peaks.py`) need no Qt at all;
* the widgets (`tests/unit/test_gui_main_window.py`) are driven through a fake
  player and a frozen clock, so "the chord follows the playhead" is asserted
  exactly, plus the toolbar a user reads, a real click on the timeline, a resize
  and an offscreen render;
* the product path (`tests/integration/test_gui_integration.py`) runs the real
  engine over a generated song - and, where the machine has an output device,
  real playback - asserting that every label on screen is the chord the session
  claims for that instant, and that `songlab gui FILE` exits cleanly.

## Planned capabilities (`[F]`, not started)

Transport: open audio, analyze, stop, play, pause, seek. *(implemented)*
Waveform, timeline, playback cursor synchronised with the audio position;
clicking a chord or a lyric seeks to it. *(implemented, without lyrics)*

Still to come: lyrics display; editing, all operating on the canonical model
(edit lyrics, edit words, edit chord labels, move/insert/delete/split/merge
chords, transpose, simplify chords) with undo/redo for every operation;
confidence shown as text (for example `Confidence: 82% — source: chroma-baseline`),
never by colour alone, so it stays accessible; an optional engine-comparison
debug view listing the final chord next to each engine's own answer, because
disagreement is information; export dialogs reusing the CLI's exporters;
translations (see `INTERNATIONALIZATION.md`).

The modules those features will need (`lyrics_editor.py`, `chord_editor.py`,
`engine_panel.py`, `settings_dialog.py`, `widgets/`) do not exist yet.

## Sequence

1. Phase 14 freezes the data model, engine interfaces, services, CLI terminology
   and exporters.
2. Phase 15 builds the GUI on top of that frozen surface. *(roadmap Phase D
   delivered the minimal window; the `[F]` features above remain)*
3. Phase 16 stabilizes English menus, dialogs, shortcuts and errors.
4. Phase 17 adds Qt Linguist translations (see `INTERNATIONALIZATION.md`).
