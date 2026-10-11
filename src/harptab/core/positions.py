"""Circle-of-fifths arithmetic and a conservative key-label heuristic."""

from dataclasses import dataclass

from harptab.models import KeyEstimate, Melody
from harptab.validation import validate_key


def harp_for(song_key: int, position: int) -> int:
    """Return the harp pitch class for a song tonic and position 1..12."""
    validate_key(song_key)
    if type(position) is not int or not 1 <= position <= 12:
        raise ValueError("position must be in 1..12")
    return (song_key - 7 * (position - 1)) % 12


def position_of(harp_key: int, song_key: int) -> int:
    """Return the circle-of-fifths position of a song tonic on a harp."""
    validate_key(harp_key)
    validate_key(song_key)
    return (7 * (song_key - harp_key)) % 12 + 1


@dataclass(frozen=True)
class KeyWeights:
    """Weights for scale coverage and tonic evidence; not a calibrated detector."""

    tonic: float = 0.1  # Reward duration on the candidate tonic.
    final_tonic: float = 0.1  # Reward ending on the candidate tonic.


def estimate_key(melody: Melody, weights: KeyWeights | None = None) -> KeyEstimate:
    """Use supplied metadata, otherwise estimate major/minor from duration and final note."""
    weights = weights or KeyWeights()
    if melody.key_estimate is not None:
        return melody.key_estimate
    if not melody.notes:
        return KeyEstimate(0, "major", 0.0)
    durations = [0.0] * 12
    for note in melody.notes:
        durations[note.pitch % 12] += note.duration
    total = sum(durations)
    scales = {"major": (0, 2, 4, 5, 7, 9, 11), "minor": (0, 2, 3, 5, 7, 8, 10)}
    candidates: list[tuple[float, int, str]] = []
    for tonic in range(12):
        for mode, scale in scales.items():
            coverage = sum(durations[(tonic + step) % 12] for step in scale) / total
            score = coverage + weights.tonic * durations[tonic] / total
            score += weights.final_tonic * (melody.notes[-1].pitch % 12 == tonic)
            candidates.append((score, tonic, mode))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    best, second = candidates[:2]
    return KeyEstimate(best[1], best[2], max(0.0, min(1.0, best[0] - second[0])))
