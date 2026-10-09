# GUI Requirements — the window Phase D implemented

> Status: **implemented, without lyrics** (roadmap Phase D, 2026-10-08). The
> window exists, is verified offscreen and on real audio, and exposes the full
> arrangement below for the features that follow.

## What exists today

`src/song_chord_lyrics_analyzer/gui/`

* `main_window.py` — `MainWindow(session, *, engines, input_hash, interval,
  parent)`, its `QToolBar` transport (Open/Play/Pause/Stop/Back/Forward with
  `QKeySequence` shortcuts), the big chord label, the clock, the state label,
  and the `TimelineWidget` + `AnalysisPanel` placed in a `QSplitter`.
* `timeline.py` — `TimelineWidget(QWidget)`: the waveform rendered from the
  session's peaks, the chord `ChordBand` strip, the playhead, and mouse
  click/drag → `seek_requested`.
* `analysis_panel.py` — `AnalysisPanel(QWidget)`: `QFormLayout` whose rows the
  presenter (`app/summary.py`) publishes and the tests read back through
  `text_rows()`. `songlab gui` shows the same data a terminal line would
  print.
* `__init__.py` — `require_qt()` (the honest import-time error when the optional
  `gui` extra is missing) and `run(audio, *, engines, input_hash, argv)`: the
  window's entry point. Qt is imported **only when the window starts**, never
  when the package is imported, so `songlab play` and `songlab info` stay
  Qt-free and the core matrix stays clean.

## Architecture (unchanged from the pre-window design)

```
audio/        decode · probe · peaks · playback      (no gui imports here)
  │  SongSession  ←──  (session owns the engine registry, the player, the
  │       ▲           timeline cache and the analysis outcome; the window
  │       │           never touches engines or widgets)
  ▼
app/          timeline presenter · summary presenter · session
  │
  ▼
gui/          thin Qt widgets over app/ data (one snapshot per tick)
```

`app/` owns all domain logic. `gui/` renders what a presenter produced; it knows
nothing about the engine, the model, numpy or the song file. `session.waveform_
peaks(buckets)` feeds the timeline.

## What is deliberately absent (Phase D, and why)

* **No `gui/player.py`.** The window drives the session's existing
  `SoundDevicePlayer`, so there is no Qt Multimedia backend and no new
  dependency. Playback stays in `app/` and the window only *draws* it.
* **No `gui/waveform.py`.** The waveform, the chord strip and the playhead are
  one widget (`TimelineWidget`) and one `x_at`/`seconds_at` mapping — one pixel
  rule, one `resizeEvent`, one autoriser.
* **No lyrics view.** `songlab lyrics` exists and the engine is registered, but
  the window shows what `app/summary.py` publishes (the Rule of the Panel:
  widgets render, presenters produce). The lyrics rows are `[F]` work.

## Sequencing and the `[F]` list

Each feature below is delivered as a *presenter* in `app/` (pure Python,
tested the same way `test_summary_presenter.py` and `test_timeline_presenter.py`
are), with one window patch to bind it. Nothing in this list may change the
CLI, the engine or the session.

1. **Lyrics view** — active `LyricSegment`/`LyricWord` lines, same clock as the
   chord band; a word highlighted when its timestamps exist.
2. **Chord/lyric editing** — click a band, type a label: the session's undo/redo
   (command pattern in `app/`) plus a consistent snapshot + persist cycle.
3. **Transpose** — a chord-level transpose whose window keeps every label in
   `CHORD_QUALITY_SUFFIX` form.
4. **Chord simplification** — drop slash/extension noise, keep a quality legend.
5. **Export dialogs** — JSON of the canonical document, ChordPro, lyric lyrics,
   plain text.
6. **Confidence/engine panels** — per-chord confidence (from the engine), the
   `Engines`/`Warnings` rows of the summary panel.
7. **Translations** — the `i18n/` package (phase 17) feeding a language menu;
   nothing here guesses a language.

## Testing constraint

`QT_QPA_PLATFORM=offscreen` makes the window testable without a display:
`tests/conftest.py` sets it once and reuses the existing `QApplication` (that is
what the `qt_app` fixture does for all of `tests/unit/test_gui_*.py`). A widget
that cannot run on the offscreen platform plugin without a display is not done;
the rest of the suite must stay Qt-free, exactly as the gate's lint job
installs `.[dev,gui]` but the matrix runs without it.

## CLI surface

```
songlab lyrics song.wav          # Phase E: the transcript, chunked, with timestamps
songlab lyrics --engine NAME ... # engine override, same contract as songlab chords
```

Outside the window, `app/` + CLI is the whole API surface; the window adds the
same commands through `gui/run`.

## Limit I will state at the end

The window is the *thin* front end. The danger of a GUI phase is a
`main_window.py` that accumulates `if kind == "lyrics"` branches, `QMessageBox`
calls everywhere and a second analysis path for the engine layer — that would
violate the `app/`-only rule this document exists to protect. Every feature in
§5 is a presenter + one binding, and nothing else.
