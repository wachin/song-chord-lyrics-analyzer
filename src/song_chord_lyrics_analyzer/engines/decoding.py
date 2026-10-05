"""Sequence decoding for frame-wise chord scores (roadmap section 20).

A chord engine produces one score vector per frame; turning those independent
per-frame scores into a *sequence* is the decoder's job. The trivial decoder
picks the best state per frame and smooths it; the roadmap section 20
experiment replaces it with a max-sum **Viterbi** over an explicit transition
model, so a chord change costs a penalty and the decoder can keep a slightly
less likely frame on the correct chord instead of flipping twice.

This module is dependency-free on purpose: it is plain arithmetic over
:class:`Sequence` inputs, so it can be tested and reasoned about without numpy
or librosa. The engine supplies the emission scores; the decoder owns only the
temporal model.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["viterbi_decode"]


def viterbi_decode(
    emissions: Sequence[Sequence[float]],
    *,
    change_penalty: float = 0.0,
) -> list[int]:
    """Decode the highest-scoring state path through ``emissions``.

    Args:
        emissions: One sequence of state scores per frame (frames × states).
            Every frame must score the same number of states; scores are
            additive (log-likelihood-like) and may be negative.
        change_penalty: Cost subtracted from the running score of every
            transition between *different* states. ``0.0`` decodes each frame
            independently; larger values favour longer, more stable chords.
            Staying in the same state is always free.

    Returns:
        The state index chosen for each frame, same length as ``emissions``.

    Raises:
        ValueError: When ``change_penalty`` is negative, a frame is empty, or
            the frames do not all score the same number of states.
    """
    if change_penalty < 0.0:
        raise ValueError(f"change_penalty must not be negative, got {change_penalty!r}")
    frames = list(emissions)
    if not frames:
        return []
    n_states = len(frames[0])
    if n_states == 0:
        raise ValueError("every frame must score at least one state")
    for index, frame in enumerate(frames):
        if len(frame) != n_states:
            raise ValueError(f"frame {index} scores {len(frame)} states, expected {n_states}")

    # score[s] is the best path score ending in state s at the current frame.
    score = [float(value) for value in frames[0]]
    # back[s][t] is the state at frame t-1 that precedes state s at frame t.
    back = [[0] * len(frames) for _ in range(n_states)]

    for t in range(1, len(frames)):
        emission = frames[t]
        updated = [0.0] * n_states
        for state in range(n_states):
            # Staying put is the candidate to beat, so it wins ties: a change
            # must be strictly better to be taken, which keeps boundaries put.
            best_previous = state
            best_value = score[state]
            for previous in range(n_states):
                if previous == state:
                    continue
                candidate = score[previous] - change_penalty
                if candidate > best_value:
                    best_value = candidate
                    best_previous = previous
            back[state][t] = best_previous
            updated[state] = best_value + float(emission[state])
        score = updated

    # Deterministic final choice: the highest score, lowest index on ties.
    last = max(range(n_states), key=lambda state: (score[state], -state))
    path = [0] * len(frames)
    path[-1] = last
    for t in range(len(frames) - 1, 0, -1):
        path[t - 1] = back[path[t]][t]
    return path
