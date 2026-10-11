"""Persistence of the edited chord layer (roadmap Phase G).

The roadmap's promise is *save, reload, and the engine's original output is
still recoverable*. The shape that keeps it is a **sidecar document** storing
the two things the :class:`~app.editing.CommandStack` is made of - the engine
base chord layer and the ordered list of edit commands. Reload folds the
commands over the base exactly as they were applied, so:

* the engine output is recoverable on its own (it is in the file, untouched);
* the effective layer after reload matches what the user saved, bit for bit,
  because floats round-trip exactly in JSON and commands address base events
  by their own start times;
* a stale command (a base that changed since saving) fails loudly with
  :class:`~utils.errors.InputError` and leaves the pure engine layer in place
  instead of silently dropping an edit.

The file is canonical JSON with the same envelope the shared codec produces:

    {"schema_version": EDITS_SCHEMA_VERSION, "document": {...}}

Unlike analysis documents this one is not produced by an engine, so a separate
version marker guards *its* format; a mismatch is an honest error, not a
warning, because folding commands over a read-decoded base is not migratable.
Nothing here imports Qt or a player; the GUI passes its stack in and out.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.app.editing import (
    CommandStack,
    DeleteChord,
    EditCommand,
    InsertChord,
    MergeChords,
    SetChordLabel,
    SplitChord,
    TrimChord,
)
from song_chord_lyrics_analyzer.models.music import ChordEvent
from song_chord_lyrics_analyzer.schema.codec import (
    SCHEMA_VERSION,
    SchemaError,
    decode,
    encode,
)
from song_chord_lyrics_analyzer.utils.errors import InputError
from song_chord_lyrics_analyzer.utils.logging import get_logger

__all__ = [
    "EDITS_SCHEMA_VERSION",
    "EditsDocument",
    "edits_sidecar_path",
    "load_edits",
    "rebuild_stack",
    "save_edits",
]

_logger = get_logger("app.persistence")

#: Version of the edits-sidcar format. Bump on breaking changes to it.
EDITS_SCHEMA_VERSION = "1"

#: How each command names itself inside the JSON document. The mapping is the
#: schema: an unknown tag raises instead of being skipped, so no saved edit can
#: silently vanish on reload.
_COMMAND_TAGS: dict[str, type] = {
    "set-label": SetChordLabel,
    "split": SplitChord,
    "merge": MergeChords,
    "trim": TrimChord,
    "delete": DeleteChord,
    "insert": InsertChord,
}
_COMMAND_FIELDS: dict[type, tuple[str, ...]] = {
    SetChordLabel: ("start", "label"),
    SplitChord: ("start", "at"),
    MergeChords: ("first_start", "second_start"),
    TrimChord: ("start", "new_start", "new_end"),
    DeleteChord: ("start",),
    InsertChord: ("at", "label", "end"),
}


@dataclass
class EditsDocument:
    """The decoded sidecar: the engine layer and the corrections over it.

    Attributes:
        chords: The engine's chord output, unmodified by anything the user did.
        commands: The applied edit commands, in the order they were pushed.
        input_path: The analysed audio file, as a string for portability.
        input_hash: The audio digest the sidecar belongs to, when known - the
            strongest check that the edits describe the right base.
        application_version: Version that wrote the sidecar, for provenance.
    """

    chords: list[ChordEvent] = field(default_factory=list)
    commands: list[EditCommand] = field(default_factory=list)
    input_path: str | None = None
    input_hash: str | None = None
    application_version: str | None = None


def edits_sidecar_path(audio_path: str | Path) -> Path:
    """Where the editable layer of ``audio_path`` lives: a sibling JSON file.

    ``song.mp3`` -> ``song.songlab.json``. A sibling keeps "rename the song,
    rename its edits" natural instead of hiding the state in a cache directory
    that dies between machines.
    """
    return Path(audio_path).with_suffix(".songlab.json")


# -- command (de)serialisation --------------------------------------------


def _command_to_json(command: EditCommand) -> dict[str, Any]:
    try:
        command_type = type(command)
        names = _COMMAND_FIELDS[command_type]
        tag = next(one for one, one_type in _COMMAND_TAGS.items() if one_type is command_type)
    except (KeyError, StopIteration) as exc:
        raise SchemaError(
            f"A {type(command).__name__} edit cannot be saved.",
            hint="Edits outside the Phase G vocabulary are not serialisable yet.",
        ) from exc
    encoded: dict[str, Any] = {"kind": tag}
    for name in names:
        value = getattr(command, name)
        encoded[name] = None if value is None else encode(value)
    return encoded


def _command_from_json(data: Any) -> EditCommand:
    if not isinstance(data, dict) or "kind" not in data:
        raise SchemaError(
            "An edit command needs a 'kind' tag.",
            hint="The saved sidecar is corrupt; edits were written by another version.",
        )
    command_type = _COMMAND_TAGS.get(data["kind"])
    if command_type is None:
        raise SchemaError(
            f"Unknown edit command kind {data['kind']!r}.",
            hint="The sidecar was written by a newer SongLab.",
        )
    names = _COMMAND_FIELDS[command_type]
    missing = [name for name in names if name not in data]
    if missing:
        raise SchemaError(f"A {command_type.__name__} edit is missing {', '.join(missing)!r}.")
    values: dict[str, Any] = {}
    for name in names:
        value = data[name]
        if name == "label":
            if not isinstance(value, str):
                raise SchemaError(f"The 'label' of an edit must be text, got {value!r}.")
            values[name] = value
        else:
            values[name] = None if value is None else float(value)
    return command_type(**values)


# -- document <-> JSON -----------------------------------------------------


def save_edits(
    stack: CommandStack,
    path: str | Path,
    *,
    input_path: str | None = None,
    input_hash: str | None = None,
) -> Path:
    """Write the sidecar for one song's edited layer; return the path written.

    Raises:
        SchemaError: When the stack carries an edit outside the vocabulary.
    """
    document = {
        "format": "songlab-edits",
        "edits_version": EDITS_SCHEMA_VERSION,
        "input_path": input_path,
        "input_hash": input_hash,
        "chords": [encode(event) for event in stack.base],
        "commands": [_command_to_json(command) for command in stack.applied],
    }
    target = Path(path)
    target.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "document": document,
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _logger.info("saved %d edit(s) to %s", len(stack), target)
    return target


def load_edits(path: str | Path) -> EditsDocument:
    """Read a sidecar into a provenance-carrying :class:`EditsDocument`.

    Raises:
        InputError: No such file.
        SchemaError: Not a SongLab edits document, wrong version, corrupted.
    """
    source = Path(path)
    if not source.is_file():
        raise InputError(
            f"No edits document at {str(source)!r}.",
            hint="Save the edits with save_edits() first.",
        )
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SchemaError(f"{source.name} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SchemaError(f"{source.name} is not a SongLab document.")
    document = payload.get("document")
    if not isinstance(document, dict) or document.get("format") != "songlab-edits":
        raise SchemaError(
            f"{source.name} is not a SongLab *edits* document.",
            hint="Other documents use the 'songlab' format, not 'songlab-edits'.",
        )
    version = document.get("edits_version")
    if version != EDITS_SCHEMA_VERSION:
        raise SchemaError(
            f"Edits schema version {version!r} differs from supported {EDITS_SCHEMA_VERSION!r}.",
            hint="Open the sidecar with the version that wrote it.",
        )
    chords_raw = document.get("chords")
    commands_raw = document.get("commands")
    if not isinstance(chords_raw, list) or not isinstance(commands_raw, list):
        raise SchemaError(f"{source.name} needs a 'chords' list and a 'commands' list.")
    decoded = EditsDocument(
        chords=[decode(ChordEvent, item) for item in chords_raw],
        commands=[_command_from_json(item) for item in commands_raw],
        input_path=document.get("input_path"),
        input_hash=document.get("input_hash"),
        application_version=None,
    )
    _logger.info(
        "loaded %d chord(s) and %d edit(s) from %s",
        len(decoded.chords),
        len(decoded.commands),
        source,
    )
    return decoded


def rebuild_stack(
    document: EditsDocument,
    *,
    on_change: Any = None,
) -> CommandStack:
    """A live :class:`CommandStack` replaying a saved document.

    Every command is re-applied over the base through ``push``, so the same
    validation that guarded the session guards the replay: a stale or corrupted
    command raises :class:`~utils.errors.InputError` and the returned stack
    stays with the commands applied so far - never a silently effective layer.

    Raises:
        InputError: A command no longer addresses its event.
    """
    stack = CommandStack(document.chords, on_change=on_change)
    for command in document.commands:
        stack.push(command)
    return stack
