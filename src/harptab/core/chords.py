"""Arrange supported harmony tones as physically playable block chords."""

from collections.abc import Iterable
from dataclasses import dataclass

from harptab.core.difficulty import OVER_NOTES, Difficulty, costs_for, node_cost, transition_cost
from harptab.core.instrument import HarmonicaModel
from harptab.core.positions import estimate_key, position_of
from harptab.core.search import _shifts
from harptab.models import (
    Action,
    ChordArrangement,
    ChordEvent,
    ChordScore,
    Melody,
    NoteEvent,
    Technique,
    Voicing,
)
from harptab.validation import validate_key, validate_score


@dataclass(frozen=True)
class ChordCosts:
    omitted_tone: float = 4.0  # Cost for an unplayed supporting pitch.
    extra_hole: float = 0.15  # Effort for each additional simultaneous hole.


def lead_melody(score: ChordScore) -> Melody:
    """Return the designated melody without changing its register or timing."""
    validate_score(score)
    return Melody(
        [NoteEvent(e.lead, e.start, e.duration, e.confidence) for e in score.events],
        score.tempo_bpm,
        score.beats,
        score.key_estimate,
        score.source,
    )


def voicings_for_event(
    event: ChordEvent,
    harp: HarmonicaModel,
    transpose: int = 0,
    *,
    overblows: bool = False,
) -> list[Voicing]:
    """Retain the lead and only source pitches; support adjacent unbent groups up to four holes."""
    validate_score(ChordScore([event]))
    if type(transpose) is not int:
        raise ValueError("transpose must be an integer number of semitones")
    targets = {p + transpose for p in event.pitches}
    lead = event.lead + transpose
    result = [
        Voicing((a,))
        for a in harp.actions_for_pitch(lead)
        if overblows or a.technique not in OVER_NOTES
    ]
    for direction in (Technique.BLOW, Technique.DRAW):
        reeds = {
            a.hole: a
            for pitch in sorted(targets)
            for a in harp.actions_for_pitch(pitch)
            if a.technique == direction
        }
        for first in range(1, 10):
            for size in range(2, min(4, 11 - first) + 1):
                holes = range(first, first + size)
                if all(h in reeds for h in holes):
                    actions = tuple(reeds[h] for h in holes)
                    if lead in {a.pitch for a in actions}:
                        result.append(Voicing(actions))
    return sorted(
        result,
        key=lambda v: tuple((a.hole, a.technique.value, a.bend_semitones) for a in v.actions),
    )


def assign_chords(
    score: ChordScore,
    harp: HarmonicaModel,
    transpose: int = 0,
    skill: str | Difficulty = "intermediate",
    *,
    overblows: bool = False,
) -> ChordArrangement:
    """Choose a low-cost path of voicings, reporting every omitted source tone."""
    melody = lead_melody(score)
    if type(transpose) is not int:
        raise ValueError("transpose must be an integer number of semitones")
    costs = costs_for(skill)
    policy = ChordCosts()
    layers = [voicings_for_event(e, harp, transpose, overblows=overblows) for e in score.events]
    indices = [i for i, layer in enumerate(layers) if layer]
    chosen: list[Voicing | None] = [None] * len(layers)

    def anchor(voicing: Voicing, index: int) -> Action:
        return next(a for a in voicing.actions if a.pitch == score.events[index].lead + transpose)

    def node(voicing: Voicing, index: int) -> float:
        missing = len(score.events[index].pitches) - len({a.pitch for a in voicing.actions})
        return (
            node_cost(anchor(voicing, index), costs)
            + policy.omitted_tone * missing
            + policy.extra_hole * (len(voicing.actions) - 1)
        )

    total = sum(
        costs.unplayable + policy.omitted_tone * (len(score.events[i].pitches) - 1)
        for i, layer in enumerate(layers)
        if not layer
    )
    if indices:
        first = indices[0]
        values = [node(v, first) for v in layers[first]]
        parents = []
        for before, index in zip(indices, indices[1:], strict=False):
            row = []
            new_values = []
            for voice in layers[index]:
                options = [
                    value + transition_cost(anchor(prev, before), anchor(voice, index), costs)
                    for prev, value in zip(layers[before], values, strict=True)
                ]
                parent = min(range(len(options)), key=lambda j: (options[j], j))
                row.append(parent)
                new_values.append(options[parent] + node(voice, index))
            parents.append(row)
            values = new_values
        state = min(range(len(values)), key=lambda j: (values[j], j))
        total += values[state]
        for layer_index in range(len(indices) - 1, -1, -1):
            index = indices[layer_index]
            chosen[index] = layers[index][state]
            if layer_index:
                state = parents[layer_index - 1][state]
    omissions = [
        len(e.pitches) - len({a.pitch for a in v.actions} if v else set())
        for e, v in zip(score.events, chosen, strict=True)
    ]
    played = [a for v in chosen if v for a in v.actions]
    stats = {
        "chords": sum(v is not None and len(v.actions) > 1 for v in chosen),
        "omitted_tones": sum(omissions),
        "incomplete_chords": sum(
            len(e.pitches) > 1 and n > 0 for e, n in zip(score.events, omissions, strict=True)
        ),
        "unplayable": sum(v is None for v in chosen),
        "bends": sum(a.bend_semitones > 0 for a in played),
        "overblows": sum(a.technique in OVER_NOTES for a in played),
    }
    tonic = (estimate_key(melody).tonic + transpose) % 12
    return ChordArrangement(harp.key, position_of(harp.key, tonic), transpose, chosen, total, stats)


def search_chords(
    score: ChordScore,
    mode: str = "play_along",
    harps: Iterable[int] | None = None,
    skill: str | Difficulty = "intermediate",
    top_n: int = 3,
    *,
    overblows: bool = False,
) -> list[ChordArrangement]:
    """Rank harmony arrangements, prioritizing a playable melody before chord coverage."""
    melody = lead_melody(score)
    costs_for(skill)
    if mode not in ("play_along", "practice"):
        raise ValueError("mode must be play_along or practice")
    if type(top_n) is not int or top_n < 1:
        raise ValueError("top_n must be a positive integer")
    keys = list(range(12) if harps is None else harps)
    if not keys:
        raise ValueError("harps must contain at least one key")
    for key in keys:
        validate_key(key)
    if not score.events:
        return []
    candidates = []
    for key in sorted(set(keys)):
        harp = HarmonicaModel(key)
        for shift in [0] if mode == "play_along" else _shifts(melody, harp):
            candidates.append(assign_chords(score, harp, shift, skill, overblows=overblows))
    candidates.sort(
        key=lambda a: (a.stats["unplayable"], a.cost, abs(a.transpose), a.harp_key, a.transpose)
    )
    return candidates[:top_n]
