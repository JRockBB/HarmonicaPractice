"""Track selection and highest-active-note (skyline) reduction."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import pairwise

from harptab.models import NoteEvent


@dataclass(frozen=True)
class TrackWeights:
    name_hint: float = 100.0  # Favor tracks explicitly named melody, vocal or lead.
    mean_pitch: float = 1.0  # Favor a higher average register.
    note_count: float = 0.1  # Favor sustained melodic activity.


def choose_track(
    tracks: Sequence[tuple[str, list[NoteEvent]]],
    weights: TrackWeights | None = None,
) -> list[NoteEvent]:
    """Select a nonempty melody track, using name hints, mean pitch and note count."""
    weights = weights or TrackWeights()
    candidates = [(name, notes) for name, notes in tracks if notes]
    if not candidates:
        return []

    def score(track: tuple[str, list[NoteEvent]]) -> float:
        name, notes = track
        hint = any(word in name.lower() for word in ("melody", "vocal", "lead"))
        return (
            weights.name_hint * hint
            + weights.note_count * len(notes)
            + weights.mean_pitch * sum(n.pitch for n in notes) / len(notes)
        )

    return max(candidates, key=score)[1]


def skyline(notes: Sequence[NoteEvent]) -> list[NoteEvent]:
    """Keep the highest sounding pitch, splitting overlaps and preserving rearticulations."""
    if not notes:
        return []
    boundaries = sorted({t for n in notes for t in (n.start, n.start + n.duration)})
    result: list[NoteEvent] = []
    previous_id: int | None = None
    for start, end in pairwise(boundaries):
        active = [(i, n) for i, n in enumerate(notes) if n.start <= start < n.start + n.duration]
        if not active:
            previous_id = None
            continue
        index, selected = max(active, key=lambda item: (item[1].pitch, item[1].start, -item[0]))
        if previous_id == index:
            result[-1] = replace(result[-1], duration=end - result[-1].start)
        else:
            result.append(replace(selected, start=start, duration=end - start))
        previous_id = index
    return result
