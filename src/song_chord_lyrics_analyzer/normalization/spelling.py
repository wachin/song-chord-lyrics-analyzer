"""Key-aware spelling of chord labels for display (roadmap Phase F).

The canonical model deliberately stores **sharp-spelled** pitch classes
(:data:`~song_chord_lyrics_analyzer.models.music.PITCH_CLASS_NAMES`), so an
analysis is reproducible and comparable across engines. A musician reading a
song in B flat, however, expects ``Bb``, ``Eb`` and ``Gm`` - not ``A#``,
``D#`` and ``F#m``. This module turns a canonical label into the spelling the
key calls for, without changing the document, the engine output or any stored
value: it is a presentation decision, like the waveform colour.

Two public entry points:

* :func:`prefers_flats` answers whether a key is conventionally written with
  flats (F, Bb, Eb, Ab, Db, Gb, Cb major and D, G, C, F, Bb, Eb, Ab minor).
  An unknown key keeps the canonical sharp spelling, because the analysis did
  not make a claim strong enough to respell.
* :func:`spell_chord_label` respells the root and the slash bass of one chord
  label, leaving its quality suffix untouched. ``N`` and ``?`` pass through.

Everything here is plain string work: no Qt, no audio, no numpy.
"""

from __future__ import annotations

from song_chord_lyrics_analyzer.models.music import NOTE_NAME_TO_PITCH_CLASS

__all__ = ["prefers_flats", "spell_chord_label", "spell_key_label", "spell_note_name"]

#: Flat spelling of each pitch class that has a conventional flat name.
_FLAT_NAMES: dict[int, str] = {
    1: "Db",
    3: "Eb",
    6: "Gb",
    8: "Ab",
    10: "Bb",
}

#: Major keys conventionally written with flats, by tonic pitch class.
#: F (5), Bb (10), Eb (3), Ab (8) and Db (1). B major (11) and F# major (6)
#: are kept sharp: their flat spellings (Cb, Gb) are not simpler, and the key
#: estimate's own label is the canonical sharp name, so respelling them would
#: make the chords disagree with the key shown.
_FLAT_MAJOR_KEYS = frozenset({1, 3, 5, 8, 10})

#: Relative minor keys conventionally written with flats: Dm (2), Gm (7),
#: Cm (0), Fm (5), Bbm (10) and Ebm (3). G# minor (8, five sharps) is simpler
#: than Ab minor (seven flats), so it stays sharp.
_FLAT_MINOR_KEYS = frozenset({0, 2, 3, 5, 7, 10})


def prefers_flats(tonic: str | None, mode: str | None) -> bool:
    """Whether a key is conventionally spelled with flats.

    Args:
        tonic: The key tonic in any accepted spelling (``"A#"`` or ``"Bb"``).
        mode: ``"major"``, ``"minor"`` (case-insensitive), or ``None`` when the
            key is unknown.

    Returns:
        ``True`` for a flat key, ``False`` for a sharp key or an unknown one.
        The fallback is conservative: an unknown key keeps the canonical
        sharp spelling rather than claiming a flat one.
    """
    if not tonic:
        return False
    pitch_class = NOTE_NAME_TO_PITCH_CLASS.get(tonic)
    if pitch_class is None:
        return False
    normalized = (mode or "").strip().lower()
    if normalized.startswith("min"):
        return pitch_class in _FLAT_MINOR_KEYS
    if normalized.startswith("maj"):
        return pitch_class in _FLAT_MAJOR_KEYS
    return False


def spell_note_name(name: str, *, prefer_flats: bool) -> str:
    """Spell one note name for display.

    The input is any accepted spelling; with ``prefer_flats`` a pitch class
    that has a conventional flat name is written flat, otherwise the canonical
    sharp name is returned unchanged. Notes without two spellings (``C``, ``E``,
    ``F``, ``B``) and unrecognised text pass through untouched.
    """
    if not prefer_flats:
        return name
    pitch_class = NOTE_NAME_TO_PITCH_CLASS.get(name)
    if pitch_class is None:
        return name
    return _FLAT_NAMES.get(pitch_class, name)


def _split_root(label: str) -> tuple[str, str] | None:
    """Split ``"C#m7/E"`` into its root and the rest (``"C#"``, ``"m7/E"``)."""
    if not label:
        return None
    length = 2 if len(label) > 1 and label[1] in "#b" else 1
    root = label[:length]
    if root not in NOTE_NAME_TO_PITCH_CLASS:
        return None
    return root, label[length:]


def spell_chord_label(label: str, *, prefer_flats: bool) -> str:
    """Respelling a whole chord label, root and slash bass included.

    ``A#m7/D#`` becomes ``Bbm7/Eb`` in a flat key, while ``N``, ``?``, unknown
    spellings and labels without a recognisable root pass through unchanged.
    The suffix is never rewritten: only the note names carry enharmonic
    alternatives.
    """
    if not prefer_flats or not label or label in {"N", "?"}:
        return label
    head, separator, bass = label.partition("/")
    split = _split_root(head)
    if split is None:
        return label
    root, suffix = split
    spelled = f"{spell_note_name(root, prefer_flats=True)}{suffix}"
    if separator and bass:
        spelled = f"{spelled}/{spell_note_name(bass, prefer_flats=True)}"
    return spelled


def spell_key_label(tonic: str | None, mode: str | None) -> str:
    """A human key name spelled the way the key is conventionally written.

    ``("A#", "major")`` becomes ``"Bb major"`` and ``("D", "minor")`` stays
    ``"D minor"``. An unknown tonic or mode returns ``"unknown"`` rather than
    inventing a key, and a mode outside major/minor keeps its name with the
    canonical tonic spelling.
    """
    if not tonic or not mode or mode.strip().lower() == "unknown":
        return "unknown"
    prefer_flats = prefers_flats(tonic, mode)
    return f"{spell_note_name(tonic, prefer_flats=prefer_flats)} {mode}"
