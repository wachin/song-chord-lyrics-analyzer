# Internationalization

## Current policy: English first

The application is English-only until it is stable. This is a deliberate
ordering decision (roadmap sections 3, 77 and 79), not an oversight:

* Python identifiers, class names, function names — English
* CLI commands, options, help text and error messages — English
* Logging, configuration keys, reports and documentation — English
* GUI text — English, from the start
* Test names and descriptions — English

Spanish and any other language are added **after** the English application stops
changing.

## What exists today

* All user-facing strings are plain English literals in the CLI layer, in
  complete sentences — never concatenated fragments. They are cheap to extract
  later precisely because no string assembling happens anywhere.
* `src/song_chord_lyrics_analyzer/i18n/` exists as an empty, documented package
  so the import path is stable when translations arrive.
* No Spanish strings exist anywhere in the codebase.

## Phase 17 plan

```text
English source strings (stabilized)
        ↓
lupdate  →  translations/song_chord_lyrics_analyzer_es.ts
        ↓
Qt Linguist (translator)
        ↓
lrelease →  *_es.qm
        ↓
QTranslator loaded at runtime
```

Rules for that phase:

1. Do not start translating while the UI changes daily.
2. Never write `label.setText("Analyze")` without making it translatable.
3. Prefer whole translatable strings; never build sentences from translated
   fragments (word order and plurals differ per language).
4. Ship the English source catalogue as the reference for translators.
5. Keep CLI text translatable through the same mechanism where practical, so the
   CLI and GUI share terminology.

Planned catalogue names:

```text
translations/
├── song_chord_lyrics_analyzer_es.ts
├── song_chord_lyrics_analyzer_fr.ts
├── song_chord_lyrics_analyzer_de.ts
└── ...
```

Spanish is the first target; French, German, Portuguese and Italian follow only
if there is demand.

## Terminology freeze

Before translations begin, the English terminology is frozen: menus, dialogs,
settings, error messages, CLI help and documentation vocabulary. Any change
after the freeze invalidates existing catalogues, so the freeze happens as part
of the architecture freeze (roadmap phase 14).
