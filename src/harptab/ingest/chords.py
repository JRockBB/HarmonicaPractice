"""Preserve simultaneous symbolic notes instead of discarding their harmony."""

from collections.abc import Sequence
from dataclasses import replace
from itertools import pairwise

from harptab.models import ChordEvent, ChordScore, Melody, NoteEvent
from harptab.validation import validate_melody, validate_score


def score_from_melody(melody: Melody) -> ChordScore:
    """Promote a reviewed monophonic melody without inventing accompaniment."""
    validate_melody(melody)
    return ChordScore(
        [ChordEvent((n.pitch,), n.start, n.duration, n.confidence) for n in melody.notes],
        melody.tempo_bpm,
        melody.beats,
        melody.key_estimate,
        melody.source,
    )


def chord_events(notes: Sequence[NoteEvent]) -> list[ChordEvent]:
    """Split at voice changes; preserve rests and repeated attacks of an identical chord."""
    for note in notes:
        validate_melody(Melody([note]))
    boundaries = sorted({t for note in notes for t in (note.start, note.start + note.duration)})
    result: list[ChordEvent] = []
    previous: tuple[int, ...] = ()
    for start, end in pairwise(boundaries):
        active = tuple(i for i, n in enumerate(notes) if n.start <= start < n.start + n.duration)
        if not active:
            previous = ()
            continue
        pitches = tuple(sorted({notes[i].pitch for i in active}))
        if active == previous:
            result[-1] = replace(result[-1], duration=end - result[-1].start)
        else:
            result.append(
                ChordEvent(pitches, start, end - start, min(notes[i].confidence for i in active))
            )
        previous = active
    validate_score(ChordScore(result))
    return result
