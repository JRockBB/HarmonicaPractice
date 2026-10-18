"""Standard-library WAV playback with recorded harmonica samples and sine tones."""

from __future__ import annotations

import sys
import wave
from array import array
from dataclasses import dataclass
from math import isfinite, pi, sin, sqrt
from pathlib import Path

from harptab.models import Arrangement, ChordArrangement, ChordScore, Melody
from harptab.playback_samples import HarmonicaSampler
from harptab.validation import validate_chord_arrangement, validate_melody

PREVIEW_VOICES = ("harmonica", "sine")


@dataclass(frozen=True)
class PreviewOptions:
    sample_rate: int = 22050  # WAV output samples per second.
    speed: float = 0.75  # Playback speed; pitch remains fixed.
    amplitude: float = 0.25  # Upper bound on peak amplitude, fraction of full-scale PCM.
    fade: float = 0.008  # Minimum attack/release ramp, seconds.
    max_duration: float = 300.0  # Maximum rendered length, seconds, to bound allocation.
    voice: str = "harmonica"  # Recorded harmonica samples; "sine" is a plain reference tone.

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
        if self.voice not in PREVIEW_VOICES:
            raise ValueError("preview voice must be harmonica or sine")


def preview_wav(
    path: str | Path,
    melody: Melody,
    arrangement: Arrangement | None = None,
    *,
    options: PreviewOptions | None = None,
) -> None:
    """Write a mono PCM WAV of the melody or its arranged pitches at a practice speed.

    Playback starts at the first note, preserving gaps and slowed durations. Unplayable
    actions remain silent. The default plays recorded harmonica notes from a bundled
    CC0 sample bank. Use ``PreviewOptions(voice="sine")`` for plain reference tones.
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
    sampler = HarmonicaSampler(p.sample_rate) if p.voice == "harmonica" else None
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
        if sampler is not None:
            samples[start:stop] = sampler.render(pitch, length, p.amplitude, p.fade)
            continue
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


def preview_chords_wav(
    path: str | Path,
    score: ChordScore,
    arrangement: ChordArrangement,
    *,
    options: PreviewOptions | None = None,
) -> None:
    """Mix the actual simultaneous reeds in a chord arrangement into a bounded mono WAV.

    Missing harmony is never synthesized. Chord voices share an onset, duration and
    breath. RMS balancing and one global peak limit prevent polyphonic clipping.
    """
    validate_chord_arrangement(score, arrangement)
    if not score.events:
        raise ValueError("a preview requires chord events")
    p = options or PreviewOptions()
    origin = score.events[0].start
    final = score.events[-1]
    duration = (final.start + final.duration - origin) / p.speed
    if not isfinite(duration) or duration > p.max_duration:
        raise ValueError(f"preview exceeds {p.max_duration:g} seconds; select a shorter excerpt")
    size = round(duration * p.sample_rate)
    if size < 1:
        raise ValueError("preview must contain at least one sample")
    mixed = array("d", [0.0]) * size
    sampler = HarmonicaSampler(p.sample_rate) if p.voice == "harmonica" else None
    for event, voice in zip(score.events, arrangement.voicings, strict=True):
        if voice is None:
            continue
        start = round((event.start - origin) * p.sample_rate / p.speed)
        stop = min(size, round((event.start + event.duration - origin) * p.sample_rate / p.speed))
        length = stop - start
        gain = 1 / sqrt(len(voice.actions))
        for action in voice.actions:
            hz = 440 * 2 ** ((action.pitch - 69) / 12)
            if hz >= p.sample_rate / 2:
                raise ValueError("preview pitch exceeds Nyquist; use a higher sample rate")
            if sampler is not None:
                signal = sampler.render(action.pitch, length, p.amplitude, p.fade)
                for i, value in enumerate(signal):
                    mixed[start + i] += value * gain
            else:
                fade = max(1, min(length // 2, round(p.fade * p.sample_rate)))
                for i in range(length):
                    envelope = min(1.0, i / fade, (length - 1 - i) / fade)
                    mixed[start + i] += (
                        32767 * p.amplitude * gain * envelope * sin(2 * pi * hz * i / p.sample_rate)
                    )
    peak = max(map(abs, mixed), default=0)
    scale = min(1.0, 32767 * p.amplitude / peak) if peak else 1.0
    samples = array("h", (round(value * scale) for value in mixed))
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(p.sample_rate)
        output.writeframes(samples.tobytes())
