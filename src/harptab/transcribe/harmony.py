"""Conservative harmony candidates around a reviewed melody in an isolated backing stem."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite

from harptab.models import ChordEvent, ChordScore, Melody
from harptab.validation import validate_melody, validate_score


@dataclass(frozen=True)
class HarmonyParams:
    lower_semitones: int = 12  # Search at most one octave below the reviewed lead.
    max_voices: int = 4  # Include at most this many simultaneous target pitches.
    min_presence: float = 0.65  # Fraction of note-interior frames supporting a pitch.
    min_relative: float = 0.20  # Fundamental amplitude relative to the lead in a frame.
    tolerance: float = 0.40  # Peak tuning tolerance in semitones around each MIDI pitch.
    frame_seconds: float = 0.10  # Spectral window length; not a new note duration.
    hop_seconds: float = 0.025  # Time between interior analysis frames.
    edge_seconds: float = 0.04  # Exclude noisy attack/release edges when possible.

    def __post_init__(self) -> None:
        if type(self.lower_semitones) is not int or not 1 <= self.lower_semitones <= 24:
            raise ValueError("lower_semitones must be an integer in 1..24")
        if type(self.max_voices) is not int or not 1 <= self.max_voices <= 4:
            raise ValueError("max_voices must be an integer in 1..4")
        for name in ("min_presence", "min_relative", "tolerance"):
            value = getattr(self, name)
            if not isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"{name} must be finite and in (0, 1]")
        for name in ("frame_seconds", "hop_seconds", "edge_seconds"):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")


def harmonize(
    melody: Melody,
    audio: Sequence[float],
    sr: int,
    *,
    params: HarmonyParams | None = None,
) -> ChordScore:
    """Add persistent lower spectral peaks without adding or extending melody events.

    Input audio must share the melody's source-time origin and ideally be an isolated
    instrumental stem. This is a reviewable candidate generator, not full polyphonic
    transcription: overtones, bleed and sustained backing can still be mistaken for notes.
    """
    try:
        import numpy as np
    except ImportError as error:
        raise ImportError("Harmony analysis requires: pip install 'harptab[audio]'") from error

    validate_melody(melody)
    if type(sr) is not int or sr <= 0:
        raise ValueError("sample rate must be a positive integer")
    samples = np.asarray(audio, dtype=np.float64)
    if samples.ndim != 1 or not np.isfinite(samples).all():
        raise ValueError("harmony audio must be a finite mono signal")
    if (
        melody.notes
        and melody.notes[-1].start + melody.notes[-1].duration > len(samples) / sr + 1 / sr
    ):
        raise ValueError("harmony audio must cover the melody's absolute source timestamps")
    p = params or HarmonyParams()
    size = max(32, round(p.frame_seconds * sr))
    fft_size = 1 << (size * 4 - 1).bit_length()
    frequencies = np.fft.rfftfreq(fft_size, 1 / sr)
    midi = 69 + 12 * np.log2(np.maximum(frequencies, 1e-9) / 440)
    window = np.hanning(size)
    padded = np.pad(samples, (size // 2, size))
    events = []
    for note in melody.notes:
        pitches = list(range(max(0, note.pitch - p.lower_semitones), note.pitch + 1))
        masks = [np.flatnonzero(abs(midi - pitch) <= p.tolerance) for pitch in pitches]
        if not len(masks[-1]):
            raise ValueError("reviewed melody pitch exceeds the harmony analysis frequency range")
        edge = min(p.edge_seconds, note.duration / 4)
        centers = np.arange(note.start + edge, note.start + note.duration - edge, p.hop_seconds)
        amplitudes = []
        for center in centers:
            start = round(float(center) * sr)
            spectrum = abs(np.fft.rfft(padded[start : start + size] * window, n=fft_size))
            local_max = np.r_[
                False, (spectrum[1:-1] > spectrum[:-2]) & (spectrum[1:-1] >= spectrum[2:]), False
            ]
            amplitudes.append(
                [
                    max((float(spectrum[i]) for i in band if local_max[i]), default=0.0)
                    for band in masks
                ]
            )
        extras: list[int] = []
        if len(amplitudes) >= 2:
            values = np.asarray(amplitudes)
            lead = values[:, -1]
            valid = lead > max(1e-6, float(np.max(lead)) * 0.1)
            # Require the lead itself to be present through most of the event.
            if valid.mean() >= p.min_presence:
                ratios = values[valid] / np.maximum(lead[valid, None], 1e-9)
                presence = np.mean(ratios >= p.min_relative, axis=0)
                candidates = [i for i in range(len(pitches) - 1) if presence[i] >= p.min_presence]
                candidates.sort(key=lambda i: (-float(np.median(ratios[:, i])), -pitches[i]))
                extras = [pitches[i] for i in candidates[: p.max_voices - 1]]
        events.append(
            ChordEvent(
                tuple(sorted([note.pitch, *extras])),
                note.start,
                note.duration,
                note.confidence,
                melody_pitch=note.pitch,
            )
        )
    score = ChordScore(events, melody.tempo_bpm, melody.beats, melody.key_estimate, melody.source)
    validate_score(score)
    return score
