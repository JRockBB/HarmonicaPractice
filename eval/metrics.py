"""Note and frame-level metrics using mir_eval, plus exact tab edit accuracy."""

from dataclasses import dataclass

import mir_eval
import numpy as np

from harptab.models import Melody
from harptab.transcribe.pitch import PitchTrack


@dataclass(frozen=True)
class Metrics:
    onset_f1: float
    offset_f1: float
    raw_pitch_accuracy: float


def score(reference: Melody, estimated: Melody, track: PitchTrack) -> Metrics:
    """Score exact MIDI pitch and ±50 ms onsets; offsets use mir_eval's default tolerance."""
    ref_intervals = np.array([(n.start, n.start + n.duration) for n in reference.notes]).reshape(
        -1, 2
    )
    est_intervals = np.array([(n.start, n.start + n.duration) for n in estimated.notes]).reshape(
        -1, 2
    )
    ref_hz = np.array([440 * 2 ** ((n.pitch - 69) / 12) for n in reference.notes])
    est_hz = np.array([440 * 2 ** ((n.pitch - 69) / 12) for n in estimated.notes])
    onset = mir_eval.transcription.precision_recall_f1_overlap(
        ref_intervals,
        ref_hz,
        est_intervals,
        est_hz,
        onset_tolerance=0.05,
        pitch_tolerance=0.01,
        offset_ratio=None,
    )[2]
    offset = mir_eval.transcription.precision_recall_f1_overlap(
        ref_intervals,
        ref_hz,
        est_intervals,
        est_hz,
        onset_tolerance=0.05,
        pitch_tolerance=0.01,
    )[2]
    times = np.array(track.times)
    expected = np.zeros(len(times))
    for note in reference.notes:
        sounding = (times >= note.start) & (times < note.start + note.duration)
        expected[sounding] = 440 * 2 ** ((note.pitch - 69) / 12)
    actual = np.nan_to_num(np.array(track.f0_hz), nan=0.0)
    ref_voicing, ref_cent, est_voicing, est_cent = mir_eval.melody.to_cent_voicing(
        times,
        expected,
        times,
        actual,
    )
    pitch_accuracy = mir_eval.melody.raw_pitch_accuracy(
        ref_voicing, ref_cent, est_voicing, est_cent
    )
    return Metrics(float(onset), float(offset), float(pitch_accuracy))


def token_accuracy(expected: list[str], actual: list[str]) -> float:
    """Normalized Levenshtein accuracy, so missing/extra notes also reduce the tab score."""
    previous = list(range(len(actual) + 1))
    for i, token in enumerate(expected, 1):
        current = [i]
        for j, other in enumerate(actual, 1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (token != other))
            )
        previous = current
    return 1 - previous[-1] / max(len(expected), len(actual), 1)
