"""Dynamic-programming assignment of melody pitches to physical actions."""

from itertools import pairwise

from harptab.core.difficulty import (
    BENDS,
    OVER_NOTES,
    Difficulty,
    action_cost,
    costs_for,
    node_cost,
    transition_cost,
)
from harptab.core.instrument import HarmonicaModel
from harptab.core.positions import estimate_key, position_of
from harptab.models import Action, Arrangement, Melody
from harptab.validation import validate_melody


def assign(
    melody: Melody,
    harp: HarmonicaModel,
    transpose: int = 0,
    skill: str | Difficulty = "intermediate",
    *,
    overblows: bool = False,
) -> Arrangement:
    """Find the least-cost action path; ``transpose`` is the total shift in semitones."""
    validate_melody(melody)
    if type(transpose) is not int:
        raise ValueError("transpose must be an integer number of semitones")
    costs = costs_for(skill)
    actions: list[Action | None] = [None] * len(melody.notes)
    layers: list[list[Action]] = []
    indices: list[int] = []
    for index, note in enumerate(melody.notes):
        candidates = [
            a
            for a in harp.actions_for_pitch(note.pitch + transpose)
            if overblows or a.technique not in OVER_NOTES
        ]
        candidates.sort(key=lambda a: (a.hole, a.technique.value, a.bend_semitones))
        if candidates:
            layers.append(candidates)
            indices.append(index)
    # Missing notes cost a constant; retaining only playable layers preserves motion across gaps.
    total = (len(melody.notes) - len(layers)) * action_cost(None, costs)
    if layers:
        scores = [node_cost(a, costs) for a in layers[0]]
        backpointers: list[list[int]] = []
        for previous, current in pairwise(layers):
            next_scores: list[float] = []
            parents: list[int] = []
            for action in current:
                options = [
                    score + transition_cost(prev, action, costs)
                    for prev, score in zip(previous, scores, strict=True)
                ]
                parent = min(range(len(options)), key=lambda i: (options[i], i))
                parents.append(parent)
                next_scores.append(options[parent] + node_cost(action, costs))
            backpointers.append(parents)
            scores = next_scores
        state = min(range(len(scores)), key=lambda i: (scores[i], i))
        total += scores[state]
        for layer in range(len(layers) - 1, -1, -1):
            actions[indices[layer]] = layers[layer][state]
            if layer:
                state = backpointers[layer - 1][state]
    played = [a for a in actions if a is not None]
    stats = {
        "bends": sum(a.technique in BENDS for a in played),
        "overblows": sum(a.technique in OVER_NOTES for a in played),
        "unplayable": len(actions) - len(played),
        "jumps": sum(abs(a.hole - b.hole) > 1 for a, b in pairwise(played)),
    }
    tonic = (estimate_key(melody).tonic + transpose) % 12
    return Arrangement(harp.key, position_of(harp.key, tonic), transpose, actions, total, stats)
