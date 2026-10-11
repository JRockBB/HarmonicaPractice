"""Original synthesized audio from the repository's public-domain melody fixtures."""

from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray

from harptab.models import Melody


@dataclass(frozen=True)
class SynthParams:
    sample_rate: int = 22050  # Output sample rate, Hz.
    amplitude: float = 0.35  # Peak scale for the lead signal.
    articulation: float = 0.06  # Silence removed from each note's tail, seconds.
    fade: float = 0.008  # Attack/release ramp length, seconds.
    tail: float = 0.1  # Final silence, seconds.
    vibrato_cents: float = 45.0  # Pitch modulation depth for vibrato variant.
    vibrato_hz: float = 5.5  # Pitch modulation rate for vibrato variant.
    noise_amplitude: float = 0.012  # Standard deviation of noise variant.
    backing_amplitude: float = 0.06  # Amplitude of each background chord tone.
    drum_amplitude: float = 0.06  # Amplitude of synthesized percussion.
    detune_cents: float = 0.0  # Global tuning offset for test signals.
    seed: int = 1729  # Reproducible noise generator seed.


def synthesize(
    melody: Melody,
    variant: str = "clean",
    params: SynthParams | None = None,
) -> tuple[NDArray[np.float32], Melody]:
    """Return additive-synth audio and the exact articulated reference melody."""
    p = params or SynthParams()
    if variant not in ("clean", "vibrato", "noise", "backing"):
        raise ValueError(f"unknown synthesized variant: {variant}")
    notes = [
        replace(note, duration=max(note.duration / 2, note.duration - p.articulation))
        for note in melody.notes
    ]
    reference = replace(melody, notes=notes)
    end = max((n.start + n.duration for n in melody.notes), default=0) + p.tail
    signal = np.zeros(round(end * p.sample_rate), dtype=np.float64)
    for note in notes:
        start = round(note.start * p.sample_rate)
        size = round(note.duration * p.sample_rate)
        time = np.arange(size) / p.sample_rate
        cents = np.full(size, p.detune_cents)
        if variant == "vibrato":
            cents += p.vibrato_cents * np.sin(2 * np.pi * p.vibrato_hz * time)
        hz = 440 * 2 ** ((note.pitch - 69 + cents / 100) / 12)
        phase = 2 * np.pi * np.cumsum(hz) / p.sample_rate
        tone = (np.sin(phase) + 0.25 * np.sin(2 * phase) + 0.1 * np.sin(3 * phase)) / 1.35
        fade = min(size // 2, round(p.fade * p.sample_rate))
        if fade:
            tone[:fade] *= np.linspace(0, 1, fade)
            tone[-fade:] *= np.linspace(1, 0, fade)
        signal[start : start + size] += p.amplitude * tone
    rng = np.random.default_rng(p.seed)
    if variant == "noise":
        signal += rng.normal(0, p.noise_amplitude, len(signal))
    if variant == "backing":
        time = np.arange(len(signal)) / p.sample_rate
        tonic = melody.key_estimate.tonic if melody.key_estimate else 0
        third = 3 if melody.key_estimate and melody.key_estimate.mode == "minor" else 4
        for semitones in (0, third, 7):
            hz = 440 * 2 ** ((48 + tonic + semitones - 69) / 12)
            signal += p.backing_amplitude * np.sin(2 * np.pi * hz * time)
        beat = 60 / (melody.tempo_bpm or 120)
        pulse = np.exp(-40 * np.remainder(time, beat))
        signal += p.drum_amplitude * pulse * rng.normal(0, 1, len(signal))
    return signal.astype(np.float32), reference
