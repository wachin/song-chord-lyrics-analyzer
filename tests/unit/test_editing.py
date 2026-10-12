"""The Phase G editing layer: chords and lyrics corrected, engine untouched.

Every promise the roadmap makes for user corrections is pinned here: chords
are addressed by start time, lyric lines by their display index, edits produce
``source="user"`` events, leave the base layers bit-identical after any number
of edits and undo/redo, reject impossible geometry loudly, and undo round-trips
exactly - across both layers of one shared tape. Qt-free, engine-free - the
command stack is exercised with plain lists.
"""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.app.editing import (
    MERGE_SOURCE,
    USER_SOURCE,
    CommandStack,
    DeleteChord,
    DeleteLyric,
    InsertChord,
    InsertLyric,
    MergeChords,
    SetChordLabel,
    SetLyricText,
    SetLyricTiming,
    SplitChord,
    TrimChord,
    effective_chords,
    effective_lyrics,
)
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricWord
from song_chord_lyrics_analyzer.models.music import ChordEvent, ChordQuality
from song_chord_lyrics_analyzer.utils.errors import InputError

BASE: list[ChordEvent] = [
    ChordEvent(start=0.0, end=1.0, root="C", quality=ChordQuality.MAJOR, source="fake"),
    ChordEvent(start=1.0, end=2.0, root="G", quality=ChordQuality.MAJOR, source="fake"),
    ChordEvent.silence(2.0, 3.0, source="fake"),
    ChordEvent(start=3.0, end=4.0, root="F", quality=ChordQuality.MAJOR, source="fake"),
]


LYRICS: list[LyricSegment] = [
    LyricSegment(
        text="uno dos",
        start=0.0,
        end=1.0,
        words=[
            LyricWord(text="uno", start=0.0, end=0.5),
            LyricWord(text="dos", start=0.5, end=1.0),
        ],
        source="fake",
    ),
    LyricSegment(text="tres cuatro", start=1.0, end=2.0, source="fake"),
    LyricSegment(text="post-coro", source="fake"),  # untimed: drawn last, never active
]


def _base_copy() -> list[ChordEvent]:
    return [event.__class__(**event.__dict__) for event in BASE]


def _sources(events: list[ChordEvent]) -> list[str | None]:
    return [event.source for event in events]


def _texts(lines: list[LyricSegment]) -> list[str]:
    return [line.text for line in lines]


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


class TestSetLyricText:
    def test_the_text_replaces_the_words_and_keeps_the_timing(self) -> None:
        edited = SetLyricText(0, "uno bien").apply(LYRICS)

        assert _texts(edited) == ["uno bien", "tres cuatro", "post-coro"]
        changed = edited[0]
        assert changed.start == 0.0 and changed.end == 1.0
        assert [word.text for word in changed.words] == ["uno", "dos"]

    def test_the_correction_is_provenance_stamped(self) -> None:
        edited = SetLyricText(1, "tres, cuatro").apply(LYRICS)
        assert edited[1].source == USER_SOURCE
        assert edited[0].source == "fake"  # the neighbours stay engine-sourced

    def test_the_engine_lines_are_never_mutated(self) -> None:
        before = _texts(LYRICS)
        SetLyricText(0, "uno bien").apply(LYRICS)
        assert _texts(LYRICS) == before
        assert LYRICS[0].source == "fake"

    def test_the_text_is_stored_trimmed(self) -> None:
        edited = SetLyricText(0, "  hola tierra  ").apply(LYRICS)
        assert edited[0].text == "hola tierra"

    def test_an_empty_line_is_rejected(self) -> None:
        with pytest.raises(InputError, match="empty"):
            SetLyricText(0, "   ")

    def test_an_unknown_index_is_rejected(self) -> None:
        with pytest.raises(InputError, match="No lyric line"):
            SetLyricText(9, "nada").apply(LYRICS)


class TestSetLyricTiming:
    def test_the_start_moves(self) -> None:
        edited = SetLyricTiming(1, new_start=1.5).apply(LYRICS)
        assert (edited[1].start, edited[1].end) == (1.5, 2.0)
        assert edited[1].source == USER_SOURCE

    def test_the_end_moves(self) -> None:
        edited = SetLyricTiming(0, new_end=0.75).apply(LYRICS)
        assert (edited[0].start, edited[0].end) == (0.0, 0.75)

    def test_an_untimed_line_gains_a_start_and_stays_open(self) -> None:
        edited = SetLyricTiming(2, new_start=0.5).apply(LYRICS)
        assert (edited[2].start, edited[2].end) == (0.5, None)
        assert edited[2].source == USER_SOURCE

    def test_an_end_before_a_start_exists_is_rejected(self) -> None:
        with pytest.raises(InputError, match="needs a start"):
            SetLyricTiming(2, new_end=1.0).apply(LYRICS)

    def test_a_line_that_would_end_where_it_starts_is_rejected(self) -> None:
        with pytest.raises(InputError, match="non-empty"):
            SetLyricTiming(0, new_end=0.0).apply(LYRICS)

    def test_a_start_past_the_end_is_rejected(self) -> None:
        with pytest.raises(InputError, match="non-empty"):
            SetLyricTiming(0, new_start=1.5).apply(LYRICS)

    def test_no_boundary_is_a_rejected_no_op(self) -> None:
        with pytest.raises(InputError, match="at least one boundary"):
            SetLyricTiming(0)

    def test_a_negative_start_is_rejected(self) -> None:
        with pytest.raises(InputError, match="negative"):
            SetLyricTiming(0, new_start=-1.0)

    def test_an_unknown_index_is_rejected(self) -> None:
        with pytest.raises(InputError, match="No lyric line"):
            SetLyricTiming(7, new_start=1.0).apply(LYRICS)


class TestDeleteLyric:
    def test_the_line_is_removed_and_the_neighbours_survive(self) -> None:
        edited = DeleteLyric(0).apply(LYRICS)

        assert _texts(edited) == ["tres cuatro", "post-coro"]
        assert [line.source for line in edited] == ["fake", "fake"]

    def test_an_unknown_index_is_rejected(self) -> None:
        with pytest.raises(InputError, match="No lyric line"):
            DeleteLyric(3).apply(LYRICS)

    def test_the_base_is_not_mutated(self) -> None:
        DeleteLyric(1).apply(LYRICS)
        assert len(LYRICS) == 3
        assert _texts(LYRICS) == ["uno dos", "tres cuatro", "post-coro"]


class TestInsertLyric:
    def test_an_untimed_line_appends_to_the_dimmed_group(self) -> None:
        edited = InsertLyric("nueva").apply(LYRICS)

        assert _texts(edited) == ["uno dos", "tres cuatro", "post-coro", "nueva"]
        assert (edited[-1].start, edited[-1].end) == (None, None)
        assert edited[-1].source == USER_SOURCE
        assert edited[-1].words == []

    def test_a_timed_line_into_free_time_is_accepted(self) -> None:
        edited = InsertLyric("puente", start=3.0, end=4.0).apply(LYRICS)
        assert (edited[-1].text, edited[-1].start, edited[-1].end) == ("puente", 3.0, 4.0)

    def test_a_line_overlapping_an_engine_line_is_rejected(self) -> None:
        with pytest.raises(InputError, match="already part of"):
            InsertLyric("invadir", start=1.5, end=1.8).apply(LYRICS)

    def test_a_line_may_not_cross_an_open_ended_line(self) -> None:
        open_ended = [*LYRICS, LyricSegment(text="fin", start=3.0, source="fake")]
        with pytest.raises(InputError, match="already part of"):
            InsertLyric("otra", start=3.5, end=4.0).apply(open_ended)

    def test_an_end_without_a_start_is_rejected(self) -> None:
        with pytest.raises(InputError, match="needs a start"):
            InsertLyric("x", end=1.0)

    def test_an_empty_line_is_rejected(self) -> None:
        with pytest.raises(InputError, match="empty"):
            InsertLyric("   ")

    def test_an_empty_span_is_rejected(self) -> None:
        with pytest.raises(InputError, match="non-empty"):
            InsertLyric("x", start=2.0, end=2.0)

    def test_a_negative_start_is_rejected(self) -> None:
        with pytest.raises(InputError, match="negative"):
            InsertLyric("x", start=-1.0)


class TestEffectiveLyrics:
    def test_commands_fold_over_the_base_in_order(self) -> None:
        edited = effective_lyrics(LYRICS, [SetLyricText(0, "uno bien"), DeleteLyric(1)])
        assert _texts(edited) == ["uno bien", "post-coro"]
        assert [line.source for line in edited] == ["user", "fake"]

    def test_a_retimed_line_jumps_to_its_new_display_position(self) -> None:
        # post-coro is untimed (drawn last); giving it 0.5 moves it between the
        # two timed lines, and the display order the commands address is the
        # order the fold re-establishes after every step.
        edited = effective_lyrics(LYRICS, [SetLyricTiming(2, new_start=0.5)])
        assert _texts(edited) == ["uno dos", "post-coro", "tres cuatro"]
        assert edited[1].start == 0.5

    def test_an_inserted_timed_line_sorts_into_playback_order(self) -> None:
        edited = effective_lyrics(LYRICS, [InsertLyric("puente", start=2.5, end=3.0)])
        assert _texts(edited) == ["uno dos", "tres cuatro", "puente", "post-coro"]

    def test_a_failing_command_leaves_the_batch_unapplied(self) -> None:
        before = _texts(LYRICS)
        with pytest.raises(InputError):
            effective_lyrics(LYRICS, [SetLyricText(0, "ok"), DeleteLyric(9)])
        assert _texts(LYRICS) == before


class TestOneTapeForBothLayers:
    """Chord and lyric commands share one tape - one Ctrl+Z covers both."""

    def test_a_lyric_command_changes_only_the_lyric_layer(self) -> None:
        stack = CommandStack(BASE, lyrics=LYRICS)
        stack.push(SetLyricText(0, "uno bien"))

        assert stack.effective_lyrics[0].text == "uno bien"
        assert [event.label for event in stack.effective] == [event.label for event in BASE]

    def test_a_chord_command_changes_only_the_chord_layer(self) -> None:
        stack = CommandStack(BASE, lyrics=LYRICS)
        stack.push(SetChordLabel(1.0, "Em"))

        assert [line.source for line in stack.effective_lyrics] == ["fake"] * 3
        assert stack.effective[1].label == "Em"

    def test_undo_walks_back_through_both_layers_in_order(self) -> None:
        stack = CommandStack(BASE, lyrics=LYRICS)
        stack.push(SetChordLabel(1.0, "Em"))
        stack.push(SetLyricText(0, "uno bien"))
        stack.push(DeleteChord(2.0))
        stack.push(DeleteLyric(1))
        assert len(stack) == 4

        stack.undo()  # the lyric deletion: the text edit before it still stands
        assert _texts(stack.effective_lyrics) == ["uno bien", "tres cuatro", "post-coro"]
        assert [event.label for event in stack.effective] == ["C", "Em", "F"]  # delete stands

        stack.undo()  # the chord deletion
        assert [event.label for event in stack.effective] == ["C", "Em", "N", "F"]
        assert stack.effective[2].start == 2.0

        stack.undo()  # the lyric relabel
        assert stack.effective_lyrics[0].text == "uno dos"

        stack.undo()  # the chord relabel
        assert [event.label for event in stack.effective] == [event.label for event in BASE]
        assert stack.can_undo is False

    def test_redo_returns_to_the_top_of_the_mixed_tape(self) -> None:
        stack = CommandStack(BASE, lyrics=LYRICS)
        stack.push(SetLyricText(0, "uno bien"))
        stack.push(SetChordLabel(1.0, "Em"))
        stack.undo()
        assert stack.can_redo

        stack.redo()
        assert stack.effective[1].label == "Em"
        assert stack.effective_lyrics[0].text == "uno bien"
        assert stack.can_redo is False

    def test_a_failed_lyric_push_leaves_the_tape_as_it_was(self) -> None:
        stack = CommandStack(BASE, lyrics=LYRICS)
        stack.push(SetLyricText(0, "uno bien"))
        with pytest.raises(InputError):
            stack.push(DeleteLyric(9))
        assert len(stack) == 1
        assert stack.effective_lyrics[0].text == "uno bien"

    def test_the_bases_survive_every_operation_untouched(self) -> None:
        stack = CommandStack(BASE, lyrics=LYRICS)
        stack.push(SetLyricText(0, "uno bien"))
        stack.push(SetLyricTiming(2, new_start=0.5))
        stack.push(DeleteLyric(1))
        stack.undo()
        stack.undo()
        stack.undo()

        assert _texts(stack.base_lyrics) == ["uno dos", "tres cuatro", "post-coro"]
        assert [line.source for line in stack.base_lyrics] == ["fake"] * 3
        assert stack.base_lyrics[0].start == 0.0 and stack.base_lyrics[0].end == 1.0
        assert [event.label for event in stack.base] == [event.label for event in BASE]
        assert _texts(stack.effective_lyrics) == _texts(stack.base_lyrics)

    def test_on_change_fires_for_lyric_edits_too(self) -> None:
        calls: list[str] = []
        stack = CommandStack(BASE, lyrics=LYRICS, on_change=lambda: calls.append("changed"))
        stack.push(SetLyricText(0, "uno bien"))
        stack.undo()
        assert calls == ["changed", "changed"]
