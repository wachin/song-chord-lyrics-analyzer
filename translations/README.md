# Translations

**Empty on purpose.** The application is English-first; translation starts only
after the English interface is frozen (roadmap sections 3, 77-79).

No Spanish or other translated strings may be added to the codebase before that
freeze. The full policy is in
[`docs/INTERNATIONALIZATION.md`](../docs/INTERNATIONALIZATION.md).

## Planned catalogues (phase 17)

```text
translations/
├── song_chord_lyrics_analyzer_es.ts    Spanish (first target)
├── song_chord_lyrics_analyzer_fr.ts    French
├── song_chord_lyrics_analyzer_de.ts    German
└── ...
```

Workflow when the time comes:

```bash
lupdate src -ts translations/song_chord_lyrics_analyzer_es.ts   # extract
# translate with Qt Linguist
lrelease translations/song_chord_lyrics_analyzer_es.ts          # compile to .qm
```

Compiled `*.qm` files are loaded at runtime through `QTranslator`. The
`src/song_chord_lyrics_analyzer/i18n/` package is reserved for that wiring.
