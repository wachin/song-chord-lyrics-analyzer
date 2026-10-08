"""The timeline presenter: where a chord lives, and where a click lands.

Two promises are pinned here. First, a band covers exactly what
``SongSession.chord_at`` claims for that instant - so a widget that paints bands
cannot show a chord the session would not report. Second, the two directions of
the seconds/pixel mapping are inverses and stay inside the track, which is what
makes "click the timeline to seek" a pure function.

No Qt here: the presenter is plain arithmetic, and that is why the window can be
tested without a display.
"""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.app.timeline import (
    ChordBand,
    chord_bands,
    position_for_x,
    x_for_position,
)
from song_chord_lyrics_analyzer.models.music import ChordEvent, ChordQuality
from song_chord_lyrics_analyzer.utils.errors import InputError

DURATION = 4.0

C = ChordEvent(start=0.0, end=1.0, root="C", quality=ChordQuality.MAJOR, source="fake")
G = ChordEvent(start=1.0, end=2.0, root="G", quality=ChordQuality.MAJOR, source="fake")
SILENCE = ChordEvent.silence(2.0, 3.0, source="fake")
F = ChordEvent(start=3.0, end=4.0, root="F", quality=ChordQuality.MAJOR, source="fake")


class TestBands:
    def test_bands_keep_the_order_and_the_labels_of_the_events(self) -> None:
        bands = chord_bands([C, G, SILENCE, F], duration=DURATION)

        assert [band.label for band in bands] == ["C", "G", "N", "F"]
        assert [band.is_silence for band in bands] == [False, False, True, False]
        assert bands[0] == ChordBand(start=0.0, end=1.0, label="C", is_silence=False)
        assert bands[3].duration == pytest.approx(1.0)

    def test_events_are_drawn_in_time_order_whatever_order_they_arrive_in(self) -> None:
        bands = chord_bands([F, SILENCE, G, C], duration=DURATION)

        assert [band.start for band in bands] == [0.0, 1.0, 2.0, 3.0]

    def test_an_event_without_an_end_runs_to_the_next_one(self) -> None:
        open_ended = ChordEvent(start=1.0, root="G", quality=ChordQuality.MAJOR)

        bands = chord_bands([C, open_ended, F], duration=DURATION)

        assert [(band.start, band.end) for band in bands] == [(0.0, 1.0), (1.0, 3.0), (3.0, 4.0)]

    def test_the_last_event_without_an_end_runs_to_the_end_of_the_track(self) -> None:
        bands = chord_bands(
            [ChordEvent(start=2.0, root="C", quality=ChordQuality.MAJOR)], duration=5.0
        )

        assert bands[0].end == 5.0

    def test_a_band_never_crosses_the_next_event_and_never_passes_the_track(self) -> None:
        overlapping = [
            ChordEvent(start=0.0, end=3.0, root="C", quality=ChordQuality.MAJOR),
            ChordEvent(start=1.0, end=9.0, root="G", quality=ChordQuality.MAJOR),
        ]

        bands = chord_bands(overlapping, duration=DURATION)

        assert [(band.start, band.end) for band in bands] == [(0.0, 1.0), (1.0, 4.0)]

    def test_bands_partition_the_track_the_way_the_session_reads_it(self) -> None:
        """Every instant is covered by the band whose label the session claims."""
        events = [C, G, SILENCE, F]
        bands = chord_bands(events, duration=DURATION)

        for step in range(0, int(DURATION * 10)):
            position = step / 10
            inside = [band for band in bands if band.start <= position < band.end]
            assert len(inside) == 1, f"{position} is covered {len(inside)} times"
            claimed = next(
                event for event in events if event.start <= position < (event.end or DURATION)
            )
            assert inside[0].label == claimed.to_label()

    def test_empty_and_zero_length_events_have_nothing_to_draw(self) -> None:
        events = [
            ChordEvent(start=1.0, end=1.0, root="C", quality=ChordQuality.MAJOR),
            ChordEvent(start=2.0, end=3.0, root="G", quality=ChordQuality.MAJOR),
        ]

        bands = chord_bands(events, duration=DURATION)

        assert [(band.start, band.end) for band in bands] == [(2.0, 3.0)]

    def test_an_event_starting_after_the_track_is_dropped(self) -> None:
        late = ChordEvent(start=9.0, end=10.0, root="C", quality=ChordQuality.MAJOR)

        assert chord_bands([F, late], duration=DURATION) == (
            ChordBand(start=3.0, end=4.0, label="F", is_silence=False),
        )

    def test_without_a_duration_an_open_ended_event_is_not_drawn(self) -> None:
        open_ended = ChordEvent(start=1.0, root="C", quality=ChordQuality.MAJOR)

        assert chord_bands([open_ended], duration=0.0) == ()

    def test_an_event_without_evidence_is_drawn_as_a_question_mark(self) -> None:
        unknown = ChordEvent(start=0.0, end=1.0)

        assert chord_bands([unknown], duration=1.0)[0].label == "?"

    def test_a_slash_chord_keeps_its_bass_in_the_label(self) -> None:
        slash = ChordEvent(start=0.0, end=1.0, root="C", quality=ChordQuality.MAJOR, bass="E")

        assert chord_bands([slash], duration=1.0)[0].label == "C/E"


class TestGeometry:
    def test_the_two_directions_are_inverses(self) -> None:
        for fraction in (0.0, 0.25, 0.5, 1.0):
            x = x_for_position(fraction * DURATION, duration=DURATION, width=800.0)
            assert position_for_x(x, duration=DURATION, width=800.0) == pytest.approx(
                fraction * DURATION
            )

    def test_the_middle_of_the_timeline_is_the_middle_of_the_track(self) -> None:
        assert x_for_position(2.0, duration=DURATION, width=400.0) == 200.0
        assert position_for_x(200.0, duration=DURATION, width=400.0) == 2.0

    def test_positions_outside_the_track_are_clamped_into_the_widget(self) -> None:
        assert x_for_position(-5.0, duration=DURATION, width=100.0) == 0.0
        assert x_for_position(99.0, duration=DURATION, width=100.0) == 100.0
        assert position_for_x(-5.0, duration=DURATION, width=100.0) == 0.0
        assert position_for_x(500.0, duration=DURATION, width=100.0) == DURATION

    def test_an_unknown_duration_maps_to_the_start_of_the_timeline(self) -> None:
        assert x_for_position(3.0, duration=0.0, width=100.0) == 0.0
        assert position_for_x(50.0, duration=0.0, width=100.0) == 0.0

    def test_a_timeline_without_width_is_an_error(self) -> None:
        with pytest.raises(InputError, match="width must be positive"):
            x_for_position(1.0, duration=DURATION, width=0.0)
        with pytest.raises(InputError, match="width must be positive"):
            position_for_x(1.0, duration=DURATION, width=-1.0)

    def test_a_negative_duration_is_an_error(self) -> None:
        with pytest.raises(InputError, match="duration must not be negative"):
            x_for_position(1.0, duration=-1.0, width=10.0)
