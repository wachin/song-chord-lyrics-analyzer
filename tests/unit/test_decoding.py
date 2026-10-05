"""Unit tests for the sequence decoder (roadmap section 20).

The Viterbi decoder is checked against an exhaustive search on small inputs, so
the test proves it optimises its own objective rather than re-asserting the
implementation's arithmetic.
"""

from __future__ import annotations

import itertools
import random

import pytest

from song_chord_lyrics_analyzer.engines.decoding import viterbi_decode


def _brute_force(emissions: list[list[float]], change_penalty: float) -> float:
    """Best achievable path score by enumerating every state sequence."""
    n_states = len(emissions[0])
    best = float("-inf")
    for path in itertools.product(range(n_states), repeat=len(emissions)):
        score = sum(emissions[t][path[t]] for t in range(len(emissions)))
        score -= change_penalty * sum(1 for t in range(1, len(path)) if path[t] != path[t - 1])
        best = max(best, score)
    return best


def _path_score(emissions: list[list[float]], path: list[int], change_penalty: float) -> float:
    score = sum(emissions[t][path[t]] for t in range(len(path)))
    score -= change_penalty * sum(1 for t in range(1, len(path)) if path[t] != path[t - 1])
    return score


class TestViterbiBasics:
    def test_empty_input_decodes_to_nothing(self) -> None:
        assert viterbi_decode([]) == []

    def test_single_frame_picks_its_highest_state(self) -> None:
        assert viterbi_decode([[0.1, 0.9, 0.4]]) == [1]

    def test_single_frame_ties_pick_the_lowest_index(self) -> None:
        assert viterbi_decode([[0.5, 0.5]]) == [0]

    def test_single_state_is_always_chosen(self) -> None:
        assert viterbi_decode([[1.0], [2.0], [3.0]]) == [0, 0, 0]

    def test_zero_penalty_decodes_each_frame_independently(self) -> None:
        emissions = [[0.1, 0.9], [0.8, 0.2], [0.3, 0.7]]
        assert viterbi_decode(emissions, change_penalty=0.0) == [1, 0, 1]

    def test_negative_penalty_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="change_penalty"):
            viterbi_decode([[0.0, 0.0]], change_penalty=-0.1)

    def test_ragged_frames_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="frame 1"):
            viterbi_decode([[0.0, 1.0], [0.0]])

    def test_empty_frame_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one state"):
            viterbi_decode([[]])


class TestViterbiBehaviour:
    def test_a_penalty_suppresses_a_short_excursion(self) -> None:
        # The single middle frame gains 0.4 by switching, but entering and
        # leaving costs 2 * 0.3 = 0.6, so the stable path wins.
        emissions = [[1.0, 0.0], [0.0, 0.4], [1.0, 0.0]]
        assert viterbi_decode(emissions, change_penalty=0.0) == [0, 1, 0]
        assert viterbi_decode(emissions, change_penalty=0.3) == [0, 0, 0]

    def test_a_clearly_better_change_is_taken(self) -> None:
        # A 0.9 gain outweighs the 0.6 round trip, so the excursion survives.
        emissions = [[1.0, 0.0], [0.0, 0.9], [1.0, 0.0]]
        assert viterbi_decode(emissions, change_penalty=0.3) == [0, 1, 0]


class TestViterbiOptimality:
    @pytest.mark.parametrize("seed", range(20))
    def test_matches_exhaustive_search(self, seed: int) -> None:
        rng = random.Random(seed)
        n_frames = rng.randint(1, 5)
        n_states = rng.randint(1, 4)
        emissions = [[rng.uniform(-1.0, 1.0) for _ in range(n_states)] for _ in range(n_frames)]
        penalty = rng.choice([0.0, 0.1, 0.35, 0.75, 1.5])

        path = viterbi_decode(emissions, change_penalty=penalty)

        assert len(path) == n_frames
        assert _path_score(emissions, path, penalty) == pytest.approx(
            _brute_force(emissions, penalty)
        )
