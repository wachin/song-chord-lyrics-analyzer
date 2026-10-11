"""The Phase G editing layer: chords corrected without touching the engine.

Every promise the roadmap makes for user corrections is pinned here: edits
address events by start time, produce ``source="user"`` events, leave the base
layer bit-identical after any number of edits and undo/redo, reject impossible
geometry loudly, and undo round-trips exactly. Qt-free, engine-free - the
command stack is exercised with plain lists.
"""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.app.editing import (
    MERGE_SOURCE,
    USER_SOURCE,
    CommandStack,
    DeleteChord,
    InsertChord,
    MergeChords,
    SetChordLabel,
    SplitChord,
    TrimChord,
    effective_chords,
)
from song_chord_lyrics_analyzer.models.music import ChordEvent, ChordQuality
from song_chord_lyrics_analyzer.utils.errors import InputError

BASE: list[ChordEvent] = [
    ChordEvent(start=0.0, end=1.0, root="C", quality=ChordQuality.MAJOR, source="fake"),
    ChordEvent(start=1.0, end=2.0, root="G", quality=ChordQuality.MAJOR, source="fake"),
    ChordEvent.silence(2.0, 3.0, source="fake"),
    ChordEvent(start=3.0, end=4.0, root="F", quality=ChordQuality.MAJOR, source="fake"),
]


def _base_copy() -> list[ChordEvent]:
    return [event.__class__(**event.__dict__) for event in BASE]


def _sources(events: list[ChordEvent]) -> list[str | None]:
    return [event.source for event in events]


class TestSetChordLabel:
    def test_the_label_replaces_the_evidence_of_one_chord(self) -> None:
        edited = SetChordLabel(1.0, "Em").apply(BASE)

        assert len(edited) == len(BASE)
        changed = edited[1]
        assert changed.root == "E"
        assert changed.quality is ChordQuality.MINOR
        assert changed.start == 1.0 and changed.end == 2.0
        assert changed.label == "Em"

    def test_the_corrected_chord_is_provenance_stamped(self) -> None:
        edited = SetChordLabel(1.0, "Em").apply(BASE)
        assert edited[1].source == USER_SOURCE
        assert _sources(edited)[0] == "fake"  # the neighbours stay engine-sourced

    def test_n_makes_the_chord_explicit_silence(self) -> None:
        edited = SetChordLabel(1.0, "N").apply(BASE)
        assert edited[1].quality is ChordQuality.NO_CHORD
        assert edited[1].label == "N"

    def test_the_engine_output_is_never_mutated(self) -> None:
        before = _base_copy()
        SetChordLabel(1.0, "Em").apply(BASE)
        assert [e.label for e in BASE] == [e.label for e in before]
        assert _sources(BASE) == _sources(before)

    def test_unknown_suffix_keeps_the_text_as_other(self) -> None:
        edited = SetChordLabel(0.0, "C13b9").apply(BASE)
        assert edited[0].root == "C"
        assert edited[0].quality is ChordQuality.OTHER
        assert edited[0].label == "C13b9"

    def test_an_unknown_start_is_rejected(self) -> None:
        with pytest.raises(InputError, match="starts at"):
            SetChordLabel(0.5, "Em").apply(BASE)

    def test_a_garbage_label_is_rejected(self) -> None:
        # "B" parses as a root, but "anana" is not a chord quality - the
        # whole label is rejected, not silently truncated to a B chord.
        with pytest.raises(InputError, match="chord quality"):
            SetChordLabel(0.0, "banana").apply(BASE)
        with pytest.raises(InputError, match="root note"):
            SetChordLabel(0.0, "xxz").apply(BASE)

    def test_flats_are_rejected_with_a_hint(self) -> None:
        with pytest.raises(InputError, match="Flats are not canonical"):
            SetChordLabel(0.0, "Bb").apply(BASE)

    def test_an_empty_label_is_rejected(self) -> None:
        with pytest.raises(InputError, match="empty"):
            SetChordLabel(0.0, "   ").apply(BASE)


class TestSplitChord:
    def test_one_chord_becomes_two_with_the_same_evidence(self) -> None:
        edited = SplitChord(0.0, 0.5).apply(BASE)

        assert len(edited) == len(BASE) + 1
        assert edited[0].start == 0.0 and edited[0].end == 0.5
        assert edited[1].start == 0.5 and edited[1].end == 1.0
        assert edited[0].root == edited[1].root == "C"
        assert all(event.source == USER_SOURCE for event in (edited[0], edited[1]))

    def test_the_neighbours_keep_their_positions(self) -> None:
        edited = SplitChord(0.0, 0.5).apply(BASE)
        assert edited[2].start == 1.0
        assert edited[-1].start == 3.0

    def test_a_split_before_the_start_is_rejected(self) -> None:
        with pytest.raises(InputError, match="after the chord start"):
            SplitChord(0.0, -0.5).apply(BASE)

    def test_a_split_past_the_end_is_rejected(self) -> None:
        with pytest.raises(InputError, match="not inside"):
            SplitChord(0.0, 2.5).apply(BASE)


class TestMergeChords:
    def test_two_adjacent_chords_become_one_spanning_both(self) -> None:
        edited = MergeChords(0.0, 1.0).apply(BASE)

        assert len(edited) == len(BASE) - 1
        merged = edited[0]
        assert merged.start == 0.0 and merged.end == 2.0
        assert merged.root == "C"  # the first chord's evidence wins
        assert merged.source == MERGE_SOURCE

    def test_merging_over_a_silence_takes_its_span(self) -> None:
        edited = MergeChords(1.0, 2.0).apply(BASE)
        merged = edited[1]
        assert merged.start == 1.0 and merged.end == 3.0
        assert merged.root == "G"

    def test_non_adjacent_chords_are_rejected(self) -> None:
        with pytest.raises(InputError, match="adjacent"):
            MergeChords(0.0, 2.0).apply(BASE)

    def test_an_unknown_second_start_is_rejected(self) -> None:
        with pytest.raises(InputError, match="starts at"):
            MergeChords(0.0, 5.0).apply(BASE)


class TestDeleteChord:
    def test_the_chord_is_removed_and_the_neighbours_survive(self) -> None:
        edited = DeleteChord(1.0).apply(BASE)

        assert len(edited) == len(BASE) - 1
        assert _sources(edited) == ["fake", "fake", "fake"]
        assert [e.start for e in edited] == [0.0, 2.0, 3.0]

    def test_deleting_silence_works_like_deleting_a_chord(self) -> None:
        edited = DeleteChord(2.0).apply(BASE)
        assert [e.start for e in edited] == [0.0, 1.0, 3.0]

    def test_an_unknown_start_is_rejected(self) -> None:
        with pytest.raises(InputError, match="starts at"):
            DeleteChord(9.0).apply(BASE)

    def test_the_base_is_not_mutated(self) -> None:
        original = _base_copy()
        DeleteChord(1.0).apply(BASE)
        assert len(BASE) == len(original)


class TestInsertChord:
    def test_a_chord_goes_into_uncovered_time(self) -> None:
        edited = InsertChord(4.0, "Am", end=5.0).apply(BASE)

        assert len(edited) == len(BASE) + 1
        inserted = edited[-1]
        assert inserted.start == 4.0 and inserted.end == 5.0
        assert inserted.root == "A" and inserted.quality is ChordQuality.MINOR
        assert inserted.source == USER_SOURCE
        assert inserted.label == "Am"

    def test_an_insertion_may_be_open_ended(self) -> None:
        edited = InsertChord(4.0, "N").apply(BASE)
        assert edited[-1].start == 4.0 and edited[-1].end is None
        assert edited[-1].is_silence

    def test_inserting_at_zero_goes_in_front_of_everything(self) -> None:
        # BASE starts at 1.0 here, so 0.0 is uncovered time before the first.
        edited = InsertChord(0.0, "G7", end=1.0).apply(BASE[1:])
        assert edited[0].start == 0.0 and edited[0].end == 1.0
        assert edited[0].quality is ChordQuality.DOMINANT7
        assert len(edited) == len(BASE)  # three base events + one insert

    def test_inserting_into_covered_time_is_rejected(self) -> None:
        with pytest.raises(InputError, match="covered"):
            InsertChord(3.999, "Am").apply(BASE)

    def test_an_empty_chord_is_rejected(self) -> None:
        with pytest.raises(InputError, match="non-empty"):
            InsertChord(3.5, "Am", end=3.5).apply(BASE)

    def test_an_unknown_label_is_rejected(self) -> None:
        with pytest.raises(InputError, match="root note"):
            InsertChord(4.0, "Xx").apply(BASE)


class TestTheNewCommandsFoldAndUndo:
    def test_delete_then_insert_folds_in_order(self) -> None:
        edited = effective_chords(
            BASE,
            [DeleteChord(1.0), InsertChord(1.0, "Em", end=2.0)],
        )
        labels = [e.label for e in edited]
        assert labels == ["C", "Em", "N", "F"]
        assert _sources(edited)[1] == USER_SOURCE

    def test_undo_removes_the_deletion_ping_pong_exact(self) -> None:
        stack = CommandStack(BASE)
        stack.push(DeleteChord(1.0))
        # Deleting G leaves [1.0, 2.0) uncovered; insert there, not into C.
        stack.push(InsertChord(1.0, "Bm", end=2.0))
        stack.undo()
        stack.undo()
        assert [e.label for e in stack.effective] == [e.label for e in BASE]
        assert len(stack.effective) == len(BASE)


class TestTrimChord:
    def test_the_start_moves_forward(self) -> None:
        edited = TrimChord(0.0, new_start=0.25).apply(BASE)
        assert edited[0].start == 0.25 and edited[0].end == 1.0

    def test_the_end_moves_earlier(self) -> None:
        edited = TrimChord(0.0, new_end=0.75).apply(BASE)
        assert edited[0].start == 0.0 and edited[0].end == 0.75

    def test_no_boundary_is_a_rejected_no_op(self) -> None:
        with pytest.raises(InputError, match="at least one boundary"):
            TrimChord(0.0).apply(BASE)

    def test_trim_to_zero_length_is_rejected(self) -> None:
        with pytest.raises(InputError, match="non-empty"):
            TrimChord(0.0, new_end=0.0).apply(BASE)

    def test_a_new_start_past_the_end_is_rejected(self) -> None:
        with pytest.raises(InputError, match="not inside"):
            TrimChord(0.0, new_start=1.5).apply(BASE)


class TestEffectiveChords:
    def test_commands_fold_over_the_base_in_order(self) -> None:
        commands: list = [SplitChord(0.0, 0.5), SetChordLabel(0.5, "Em")]
        edited = effective_chords(BASE, commands)
        assert [e.label for e in edited][:3] == ["C", "Em", "G"]

    def test_the_base_survives_a_failing_batch(self) -> None:
        original = _base_copy()
        with pytest.raises(InputError):
            effective_chords(BASE, [SetChordLabel(1.0, "Em"), SetChordLabel(7.0, "Xx")])
        assert [e.label for e in BASE] == [e.label for e in original]

    def test_the_result_is_sorted_by_start(self) -> None:
        # A split inserts before the base's later events; the fold must keep
        # playback order regardless.
        edited = effective_chords(BASE, [SplitChord(0.0, 0.25)])
        starts = [e.start for e in edited]
        assert starts == sorted(starts)


class TestCommandStack:
    def test_push_applies_and_the_effective_layer_matches(self) -> None:
        stack = CommandStack(BASE)
        stack.push(SetChordLabel(1.0, "Em"))

        labels = [e.label for e in stack.effective]
        assert labels == ["C", "Em", "N", "F"]

    def test_undo_takes_the_last_command_back(self) -> None:
        stack = CommandStack(BASE)
        stack.push(SetChordLabel(1.0, "Em"))
        stack.push(SplitChord(0.0, 0.5))

        stack.undo()
        labels = [e.label for e in stack.effective]
        assert labels == ["C", "Em", "N", "F"]
        assert len(stack.effective) == 4

        stack.undo()
        assert [e.label for e in stack.effective] == [e.label for e in BASE]

    def test_redo_reapplies_what_undo_removed(self) -> None:
        stack = CommandStack(BASE)
        stack.push(SetChordLabel(1.0, "Em"))
        stack.undo()
        assert stack.can_redo

        stack.redo()
        assert stack.effective[1].label == "Em"
        assert stack.can_redo is False

    def test_push_after_undo_discards_the_redo_tape(self) -> None:
        stack = CommandStack(BASE)
        stack.push(SetChordLabel(1.0, "Em"))
        stack.undo()
        stack.push(SetChordLabel(0.0, "Am"))

        assert stack.can_redo is False
        assert stack.effective[0].label == "Am"
        assert stack.effective[1].label == "G"

    def test_undo_without_history_is_none(self) -> None:
        stack = CommandStack(BASE)
        assert stack.undo() is None
        assert stack.redo() is None

    def test_the_base_layer_is_never_touched(self) -> None:
        original = _base_copy()
        stack = CommandStack(BASE)
        stack.push(SplitChord(0.0, 0.5))
        stack.push(MergeChords(0.0, 0.5))
        stack.push(TrimChord(0.0, new_end=0.25))
        stack.undo()
        stack.undo()
        stack.undo()
        assert [e.label for e in stack.base] == [e.label for e in original]
        assert [e.label for e in stack.effective] == [e.label for e in original]
        assert _sources(stack.effective) == _sources(original)

    def test_on_change_fires_on_push_undo_and_redo(self) -> None:
        calls: list[str] = []
        stack = CommandStack(BASE, on_change=lambda: calls.append("changed"))
        stack.push(SetChordLabel(1.0, "Em"))
        stack.undo()
        stack.redo()
        assert calls == ["changed", "changed", "changed"]

    def test_a_bad_push_raises_and_leaves_no_trace(self) -> None:
        stack = CommandStack(BASE)
        stack.push(SetChordLabel(1.0, "Em"))
        with pytest.raises(InputError):
            stack.push(SetChordLabel(9.0, "Em"))
        assert len(stack) == 1
        assert stack.effective[1].label == "Em"
