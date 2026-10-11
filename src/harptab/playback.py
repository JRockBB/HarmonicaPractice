"""A small standard-library reference-tone player for checking practice notes."""

import sys
import wave
from array import array
from dataclasses import dataclass
from math import isfinite, pi, sin
from pathlib import Path

from harptab.models import Arrangement, Melody
from harptab.validation import validate_melody


@dataclass(frozen=True)
class PreviewOptions:
    sample_rate: int = 22050  # WAV output samples per second.
    speed: float = 0.75  # Playback speed; pitch remains fixed.
    amplitude: float = 0.25  # Peak sine amplitude, fraction of full-scale PCM.
    fade: float = 0.008  # Attack/release ramp, seconds.
    max_duration: float = 300.0  # Maximum rendered length, seconds, to bound allocation.

    def __post_init__(self) -> None:
        if type(self.sample_rate) is not int or not 8000 <= self.sample_rate <= 48000:
            raise ValueError("preview sample_rate must be an integer in 8000..48000 Hz")
        if not isfinite(self.speed) or not 0 < self.speed <= 1:
            raise ValueError("preview speed must be in (0, 1]")
        if not isfinite(self.amplitude) or not 0 < self.amplitude <= 1:
            raise ValueError("preview amplitude must be in (0, 1]")
        if not isfinite(self.fade) or self.fade <= 0:
            raise ValueError("preview fade must be finite and positive")
        if not isfinite(self.max_duration) or not 0 < self.max_duration <= 3600:
            raise ValueError("preview max_duration must be in (0, 3600] seconds")


def preview_wav(
    path: str | Path,
    melody: Melody,
    arrangement: Arrangement | None = None,
    *,
    options: PreviewOptions | None = None,
) -> None:
    """Write a mono PCM WAV of the melody or its arranged pitches at a practice speed.

    Playback starts at the first note, preserving gaps and slowed durations. Unplayable
    actions remain silent. These are reference tones, not a simulated harmonica performance.
    """
    validate_melody(melody)
    if not melody.notes:
        raise ValueError("a preview requires melody notes")
    p = options or PreviewOptions()
    if arrangement is not None and len(arrangement.actions) != len(melody.notes):
        raise ValueError("arrangement must have one action per melody note")
    origin = melody.notes[0].start
    final = melody.notes[-1]
    duration = (final.start + final.duration - origin) / p.speed
    if not isfinite(duration) or duration > p.max_duration:
        raise ValueError(f"preview exceeds {p.max_duration:g} seconds; select a shorter excerpt")
    size = round(duration * p.sample_rate)
    if size < 1:
        raise ValueError("preview must contain at least one sample")
    samples = array("h", [0]) * size
    for index, note in enumerate(melody.notes):
        pitch = note.pitch
        if arrangement is not None:
            action = arrangement.actions[index]
            if action is None:
                continue
            if action.pitch != note.pitch + arrangement.transpose:
                raise ValueError("action pitch must match the transposed melody note")
            pitch = action.pitch
        if type(pitch) is not int or not 0 <= pitch <= 127:
            raise ValueError("preview pitches must be MIDI integers in 0..127")
        hz = 440 * 2 ** ((pitch - 69) / 12)
        if hz >= p.sample_rate / 2:
            raise ValueError("preview pitch exceeds Nyquist; use a higher sample rate")
        start = round((note.start - origin) * p.sample_rate / p.speed)
        stop = min(size, round((note.start + note.duration - origin) * p.sample_rate / p.speed))
        length = stop - start
        fade = max(1, min(length // 2, round(p.fade * p.sample_rate)))
        for i in range(length):
            envelope = min(1.0, i / fade, (length - 1 - i) / fade)
            samples[start + i] = round(
                32767 * p.amplitude * envelope * sin(2 * pi * hz * i / p.sample_rate)
            )
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(p.sample_rate)
        output.writeframes(samples.tobytes())
