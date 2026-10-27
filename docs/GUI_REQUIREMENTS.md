# GUI Requirements — the window Phase D implemented

> Status: **implemented** (roadmap Phase D, 2026-10-08; lyrics view
> 2026-10-09; chord and lyric editing with persistence 2026-10-10..12;
> transpose/simplify/export 2026-10-13; analysis off the UI thread and the
> language menu 2026-10-14..15; **chord chart over the lyrics** 2026-10-21;
> **plain-text chart import** 2026-10-27).
> The window exists, is verified offscreen and on real audio, and exposes the
> full arrangement below for the features that follow.

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
* the window's menus — the transport toolbar above plus Edit (chord and lyric
  editing, transpose, simplify, "Load lyrics from file..."), Export and
  **Language**, the last one built by `i18n/` (next section).

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
* ~~No lyrics view.~~ **Delivered 2026-10-09** (`[F]` item 1): the window shows
  the active `LyricSegment` and highlights the active `LyricWord`, from the same
  snapshot the chord label is drawn from (presenters in `app/lyrics_view.py`,
  the widget in `gui/lyrics_view.py`); untimed segments are drawn after the
  timed ones, dimmed, and never become active. **Closed through the session
  layer 2026-10-10** (Phase F): `SongSession.lyric_at()` / `word_at()` answer
  the lyrics layer exactly as `chord_at()` answers the chords layer, and the
  window's refresh feeds both widgets from that one snapshot — the widget's
  `set_active(segment, word)` decides nothing about the clock.
* ~~No chords above the lyrics.~~ **Delivered 2026-10-21** (`[F]` item 1b): the
  lyrics view is now a **chord chart**. `app/chord_lyrics.py` places each chord
  above the timed word whose `start <= chord.start < end` (proportional
  fallback when a line has no word timestamps), gives instrumental intro/break
  chords their own chord-only rows, never repeats a chord that merely spans
  into the next line, and nudges colliding labels apart instead of overwriting
  them. `gui/lyrics_view.py` draws each row as one monospace chord line plus
  one lyric line in the same `QTextBlock`, which keeps the block→display-index
  mapping exact for the lyric commands; the active chord is highlighted from
  the same frame as the big chord label. Flat keys are respelled for display by
  `normalization/spelling.py` (`Bb`, `Eb`, `Ab`) while the canonical document
  keeps its sharp pitch classes. Tests: `tests/unit/test_chord_lyrics.py`,
  `tests/unit/test_spelling.py`, `tests/unit/test_gui_lyrics_view.py` and
  `TestChordsAboveTheLyrics` in `tests/unit/test_gui_main_window.py`.

## Sequencing and the `[F]` list

Each feature below is delivered as a *presenter* in `app/` (pure Python,
tested the same way `test_summary_presenter.py` and `test_timeline_presenter.py`
are), with one window patch to bind it. Nothing in this list may change the
CLI, the engine or the session.

1. ~~**Lyrics view**~~ **(done, 2026-10-09)** — active `LyricSegment`/
   `LyricWord` lines, same clock as the chord band; a word highlighted when its
   timestamps exist. Presenters: `app/lyrics_view.py` (`lyric_lines`,
   `lyric_at`, `word_at`); widget: `gui/lyrics_view.py`; bind: the window's
   `open_file`/`refresh`.
   **External lyric bases (Phase F) 2026-10-14**: the Edit menu's "Load
   lyrics from file..." (Ctrl+L) parses a `.lrc`/`.srt` file with the shared
   `alignment/` package and swaps the tape's lyric base
   (`with_lyric_base`): the file wins over the engine transcription, the old
   tape's lyric commands go out with the base they addressed, chord work
   stays undoable, and the new base is saved to the Phase G sidecar by
   `Ctrl+S` like any other edit. The same parse backs `songlab analyze
   --lyrics-from FILE`.
1b. ~~**Chord chart over the lyrics**~~ **(done, 2026-10-21)** — the chord rows
   are placed by `app/chord_lyrics.py` and painted by `gui/lyrics_view.py`, with
   instrumental gap rows, active-chord highlighting and flat-key spelling. The
   alignment is word-onset resolution, the finest timestamp the lyric layer
   carries; a chord change inside a long held word lands on that word. This is
   not a beat-level alignment claim. Chart rows are drawn with `NoWrap`, so a
   long lyric line scrolls horizontally instead of wrapping under a chord row
   that would no longer line up.

1c. **Import a plain-text chord chart** — `[~]` (2026-10-27). **Edit → Load
   chord chart...** (`Ctrl+Shift+L`) parses the chart, times its chords from the
   detected sequence, times its lyric lines from the transcript's words, and
   replaces both bases through `with_chart_bases`; the status bar reports
   unmatched layers and the base is saved by `Ctrl+S`. `app/chart_import.py`
   holds the importer, `tests/unit/test_chart_import.py` the timing rules and
   `TestImportingAChordChart` the window flow. Still open: deriving timing from
   the chart's own sections/chord columns, recording the chart path in
   provenance, and manual correction of a badly aligned line.
2. ~~**Chord/lyric editing**~~ **(done, 2026-10-12)** — chords first, 2026-10-10 with persistence
   2026-10-11: `app/editing.py` holds the command tape (`SetChordLabel`,
   `SplitChord`, `MergeChords`, `TrimChord`, `DeleteChord`, `InsertChord`,
   `CommandStack`) over an immutable engine base; the timeline's context menu
   offers all six chord commands (edit/split/trim-start/trim-end/merge/delete/
   insert, each addressed by the chord under the click, with enable states
   computed from the effective layer), `Ctrl+Z`/`Ctrl+Shift+Z` undo and redo,
   and the chord label + strip redraw from the effective layer. Closing with
   unsaved edits offers Save/Cancel/Discard - exact, not a dirty flag: the
   tape is compared with the last save, so undoing back to the saved state
   closes silently.
   `app/persistence.py` saves/reloads the edits as a sibling
   `song.songlab.json` (engine chords + ordered commands, own
   `edits_version: "1"`); the engine layer stays recoverable from the file and
   a stale command fails loudly on replay. Wired into the window the same
   day: `Ctrl+S` / "Save Edits" writes the sidecar, `open_file` replays it
   automatically, and a corrupt or stale sidecar is reported with the engine
   layer kept.
   **Delivered for lyrics 2026-10-12**: four commands (`SetLyricText`,
   `SetLyricTiming`, `DeleteLyric`, `InsertLyric`) over an immutable lyric
   base on the *same* tape - one `Ctrl+Z` walks back through chords and lyrics
   in order. Right-click a line in the lyrics view for its menu (Edit text... /
   Set start... / Set end... / Insert line... / Delete line), enable states
   from the effective layer ("set end" waits for a start); the view draws the
   effective layer, so an edited line - and the active-line highlight - is in
   step the moment its command is pushed. Lines are addressed by display index
   (a line may carry no timestamp at all). The sidecar saves the engine lyric
   base beside the chords (`edits_version` stays `"1"`: a pre-lyric sidecar
   loads with an empty lyric layer, a build that predates the lyric commands
   rejects one loudly), and a lyric edit counts as unsaved for the close
   prompt like any chord edit. Word-level *timings* stay the engine's: per-word
   editing would need word addressing and is a later, separate decision.
3. ~~**Transpose**~~ **(done, 2026-10-13)** — "Transpose all chords..." asks
   for the semitone offset (-11..+11; a cancelled dialog changes nothing) and
   pushes a `TransposeDocument` command; every re-rendered label stays in
   `CHORD_QUALITY_SUFFIX` form (slash chords transpose the bass too). The
   transform acts on the *effective* layer (originals preserved underneath)
   and rides the same tape as the per-chord edits: one `Ctrl+Z` takes a whole
   song's transpose back like any other edit, and `Ctrl+S` persists it.
   The flag-first workflow is on the CLI: `songlab export --transpose N`.
4. ~~**Chord simplification**~~ **(done, 2026-10-13)** — "Simplify all chords"
   pushes a `SimplifyDocument` command built on the tested
   `contract_chord_label()` reduction (extensions/alterations drop to the
   plain triad or seventh, slash basses are removed); the same transform is
   reachable as `songlab export --simplify`.
5. ~~**Export dialogs**~~ **(done, 2026-10-13)** — "Export document..." on the
   transport toolbar (Ctrl+Shift+E): a save dialog proposing a sibling file of
   the song with a JSON / ChordPro / Markdown filter, writing through the same
   `export_document()` seam `songlab export` uses — the effective layers (edits
   included) are what gets written, so the file cannot drift from the window.
   Qt's rule stands: the picked filter names the format; a name typed over the
   proposal keeps its meaning via the suffix when no filter of ours is
   reported. A failed write is reported, a cancelled dialog changes nothing.
   With this, every `[F]` item above 7 is delivered; of the two remaining,
   the confidence/engine panels (item 6) landed 2026-10-14 and only
   translations (item 7) are open.
6. ~~**Confidence/engine panels**~~ **(delivered 2026-10-14; fed by real values
   since 2026-10-20)** — confidence is shown where it exists and named as
   `unknown` where it does not, never invented: the summary panel's "Chord
   confidence" row averages the values the chord engine reported, and the chord
   label's tooltip carries the confidence of the chord under the playhead
   (`DisplayFrame.chord_confidence_text`, empty where no chord is claimed). The
   panels did not change when the engine started reporting confidence (roadmap
   Phase I P2): the same row now shows a measured average instead of `unknown`,
   which is what this item promised — no UI work was needed for the new value.
   The `Engines` row was already there; the `Warnings` row shows the warnings
   themselves instead of their count.
7. **Translations** — **half delivered 2026-10-14/15**: `i18n/` (phase 17) owns
   the catalogue story and the window's Language menu is built from it —
   `available_languages()` lists only compiled catalogues that are actually
   installed next to the checkout, `install_translator()` loads one onto the
   `QApplication`, and the translator is held by the window because Qt drops a
   translation the moment its translator is collected; a catalogue that is
   missing or unreadable is an error, never a silent fall back to English.
   Nothing guesses a language from the environment: English (the source
   strings in the code) is the default and the only entry until a catalogue
   ships. **Open:** no catalogue is shipped (`translations/` holds only its
   `README.md`), so no language can actually be selected yet — the menu is
   wiring, not translation. The `.ts`/`lrelease` workflow is recorded in
   `docs/INTERNATIONALIZATION.md`.

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
