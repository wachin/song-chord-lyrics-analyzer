"""Persistence of the edited layer: save, reload, recover (Phase G).

The promises pinned here are the roadmap's: a save/reload round-trip
reconstructs the effective layer exactly, the engine layer is recoverable
untouched inside the file, the sidecar records provenance (path, hash), and a
corrupt, foreign or stale document fails loudly without inventing a layer.
Qt-free, engine-free - plain files in a ``tmp_path``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from song_chord_lyrics_analyzer.app.editing import (
    CommandStack,
    MergeChords,
    SetChordLabel,
    SplitChord,
    TrimChord,
)
from song_chord_lyrics_analyzer.app.persistence import (
    EDITS_SCHEMA_VERSION,
    edits_sidecar_path,
    load_edits,
    rebuild_stack,
    save_edits,
)
from song_chord_lyrics_analyzer.models.music import ChordEvent, ChordQuality
from song_chord_lyrics_analyzer.utils.errors import InputError, SchemaError

BASE: list[ChordEvent] = [
    ChordEvent(start=0.0, end=1.0, root="C", quality=ChordQuality.MAJOR, source="fake"),
    ChordEvent(start=1.0, end=2.0, root="G", quality=ChordQuality.MAJOR, source="fake"),
    ChordEvent.silence(2.0, 3.0, source="fake"),
]


def _a_stack() -> CommandStack:
    stack = CommandStack(BASE)
    stack.push(SetChordLabel(1.0, "Em"))
    stack.push(SplitChord(0.0, 0.5))
    return stack


class TestSaveAndReload:
    def test_the_round_trip_reconstructs_the_effective_layer(self, tmp_path) -> None:
        stack = _a_stack()
        sidecar = save_edits(stack, tmp_path / "song.mp3.songlab.json")

        reloaded = rebuild_stack(load_edits(sidecar))
        before = [(e.start, e.end, e.label, e.source) for e in stack.effective]
        after = [(e.start, e.end, e.label, e.source) for e in reloaded.effective]
        assert after == before

    def test_every_bit_of_the_effective_layer_survives(self, tmp_path) -> None:
        stack = _a_stack()
        stack.push(TrimChord(0.5, new_end=0.75))
        stack.push(MergeChords(0.5, 1.0))
        sidecar = save_edits(stack, tmp_path / "x.songlab.json")

        reloaded = rebuild_stack(load_edits(sidecar))
        assert [(e.start, e.end, e.label) for e in reloaded.effective] == [
            (e.start, e.end, e.label) for e in stack.effective
        ]

    def test_the_engine_layer_is_recoverable_inside_the_file(self, tmp_path) -> None:
        sidecar = save_edits(_a_stack(), tmp_path / "song.songlab.json")

        document = load_edits(sidecar)
        assert [(e.start, e.label) for e in document.chords] == [
            (0.0, "C"),
            (1.0, "G"),
            (2.0, "N"),
        ]
        assert all(event.source == "fake" for event in document.chords)
        # ... and a fresh stack over it replays the pure engine output.
        fresh = CommandStack(document.chords)
        assert [e.label for e in fresh.effective] == ["C", "G", "N"]

    def test_the_reloaded_stack_undo_redo_works(self, tmp_path) -> None:
        stack = _a_stack()
        sidecar = save_edits(stack, tmp_path / "song.songlab.json")

        reloaded = rebuild_stack(load_edits(sidecar))
        assert reloaded.undo() is not None
        assert reloaded.can_redo
        assert len(reloaded) == 1
        # The split is undone; the Em relabel still stands.
        assert [e.label for e in reloaded.effective] == ["C", "Em", "N"]

    def test_provenance_is_saved_and_read_back(self, tmp_path) -> None:
        sidecar = save_edits(
            _a_stack(),
            tmp_path / "song.songlab.json",
            input_path="/music/song.mp3",
            input_hash="deadbeef",
        )
        document = load_edits(sidecar)
        assert document.input_path == "/music/song.mp3"
        assert document.input_hash == "deadbeef"

    def test_the_sidecar_is_valid_json(self, tmp_path) -> None:
        sidecar = save_edits(_a_stack(), tmp_path / "song.songlab.json")
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "1"
        document = payload["document"]
        assert document["format"] == "songlab-edits"
        assert document["edits_version"] == EDITS_SCHEMA_VERSION
        assert [c["kind"] for c in document["commands"]] == ["set-label", "split"]

    def test_the_default_sidecar_path_is_a_sibling(self, tmp_path) -> None:
        audio = tmp_path / "song.mp3"
        path = edits_sidecar_path(audio)
        assert path == tmp_path / "song.songlab.json"
        assert path.parent == audio.parent


class TestRejections:
    def test_an_unknown_command_kind_is_rejected_on_load(self, tmp_path) -> None:
        sidecar = save_edits(_a_stack(), tmp_path / "song.songlab.json")
        payload: dict[str, Any] = json.loads(sidecar.read_text(encoding="utf-8"))
        payload["document"]["commands"][0]["kind"] = "mind-control"
        sidecar.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(SchemaError, match="mind-control"):
            load_edits(sidecar)

    def test_a_corrupt_command_is_rejected_on_load(self, tmp_path) -> None:
        sidecar = save_edits(_a_stack(), tmp_path / "song.songlab.json")
        payload: dict[str, Any] = json.loads(sidecar.read_text(encoding="utf-8"))
        del payload["document"]["commands"][0]["start"]
        sidecar.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(SchemaError, match="missing"):
            load_edits(sidecar)

    def test_a_wrong_sidecar_format_is_rejected(self, tmp_path) -> None:
        sidecar = tmp_path / "song.songlab.json"
        sidecar.write_text(
            json.dumps({"schema_version": "1", "document": {"format": "songlab"}}),
            encoding="utf-8",
        )
        with pytest.raises(SchemaError, match="edits"):
            load_edits(sidecar)

    def test_a_wrong_edits_version_is_rejected(self, tmp_path) -> None:
        sidecar = save_edits(_a_stack(), tmp_path / "song.songlab.json")
        payload: dict[str, Any] = json.loads(sidecar.read_text(encoding="utf-8"))
        payload["document"]["edits_version"] = "999"
        sidecar.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(SchemaError, match="999"):
            load_edits(sidecar)

    def test_a_missing_file_says_what_is_missing(self, tmp_path) -> None:
        with pytest.raises(InputError, match="No edits document"):
            load_edits(tmp_path / "nope.songlab.json")


class TestStaleReplay:
    def test_a_stale_command_fails_loudly_and_keeps_the_base(self, tmp_path) -> None:
        # Saved against the three-chord base, replayed over a base where the
        # G is gone: the label edit cannot address 1.0 any more.
        stack = CommandStack(BASE)
        stack.push(SetChordLabel(1.0, "Em"))
        sidecar = save_edits(stack, tmp_path / "song.songlab.json")
        document = load_edits(sidecar)

        stale_base = [event for event in BASE if event.start != 1.0]
        with pytest.raises(InputError, match="starts at"):
            rebuild_stack(type(document)(chords=stale_base, commands=document.commands))

    def test_the_reloaded_source_stamps_are_users(self, tmp_path) -> None:
        stack = _a_stack()
        sidecar = save_edits(stack, tmp_path / "song.songlab.json")
        reloaded = rebuild_stack(load_edits(sidecar))
        assert "user" in [e.source for e in reloaded.effective]
        assert "fake" in [e.source for e in reloaded.effective]
