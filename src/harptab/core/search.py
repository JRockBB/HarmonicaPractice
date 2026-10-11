"""Rank harmonicas and transpositions using the actual assigned action path."""

from collections.abc import Iterable
from math import ceil, floor

from harptab.core.assign import assign
from harptab.core.difficulty import Difficulty, costs_for
from harptab.core.instrument import HarmonicaModel
from harptab.models import Arrangement, Melody
from harptab.validation import validate_key, validate_melody


def _shifts(melody: Melody, harp: HarmonicaModel) -> list[int]:
    low, high = harp.range()
    bottom = min(note.pitch for note in melody.notes)
    top = max(note.pitch for note in melody.notes)
    # Include partial fits for melodies wider than the instrument, as well as full fits.
    shifts = {0}
    for semitones in range(-6, 6):
        first = ceil((low - top - semitones) / 12)
        last = floor((high - bottom - semitones) / 12)
        shifts.update(semitones + 12 * octave for octave in range(first, last + 1))
    return sorted(shifts)


def search(
    melody: Melody,
    mode: str = "play_along",
    harps: Iterable[int] | None = None,
    skill: str | Difficulty = "intermediate",
    top_n: int = 3,
    *,
    overblows: bool = False,
) -> list[Arrangement]:
    """Rank complete arrangements. Play-along preserves pitches; practice permits shifts."""
    validate_melody(melody)
    costs = costs_for(skill)
    if mode not in ("play_along", "practice"):
        raise ValueError("mode must be play_along or practice")
    if type(top_n) is not int or top_n < 1:
        raise ValueError("top_n must be a positive integer")
    keys = list(range(12) if harps is None else harps)
    if not keys:
        raise ValueError("harps must contain at least one key")
    for key in keys:
        validate_key(key)
    if not melody.notes:
        return []
    candidates: list[Arrangement] = []
    for key in sorted(set(keys)):
        harp = HarmonicaModel(key)
        shifts = [0] if mode == "play_along" else _shifts(melody, harp)
        candidates.extend(
            assign(melody, harp, shift, costs, overblows=overblows) for shift in shifts
        )

    def rank(item: Arrangement) -> tuple[float, int, int, int, int, int]:
        position_preference = {1: 0, 2: 1}.get(item.position, 2)
        return (
            item.cost,
            position_preference,
            abs(item.transpose),
            item.harp_key,
            item.transpose,
            item.position,
        )

    candidates.sort(key=rank)
    return candidates[:top_n]
