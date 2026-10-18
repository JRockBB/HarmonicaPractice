"""Play the bundled CC0 harmonica recordings using only the standard library."""

from __future__ import annotations

import json
import sys
import wave
from array import array
from dataclasses import dataclass
from importlib.resources import files
from io import BytesIO
from math import ceil, cos, pi, sin


@dataclass(frozen=True)
class _SamplerParams:
    lobes: int = 12  # Windowed-sinc support, in periods of the resampling cutoff.
    phases: int = 256  # Fractional source-frame positions in the interpolation table.
    bandwidth: float = 0.9  # Guard band below output Nyquist for alias suppression.
    release: float = 0.025  # Fade within the note, seconds; rests remain silent.


@dataclass(frozen=True)
class _Sample:
    pcm: tuple[float, ...]
    loop_start: int
    loop_end: int  # Exclusive.


def _resample(sample: _Sample, step: float, frames: int, params: _SamplerParams) -> _Sample:
    """Pitch/rate conversion with a low-pass kernel and the source's sustain loop."""
    if step == 1:
        return sample
    cutoff = min(1.0, params.bandwidth / step)
    radius = ceil(params.lobes / cutoff)
    offsets = range(-radius + 1, radius + 1)
    kernels = []
    for phase in range(params.phases):
        fraction = phase / params.phases
        weights = []
        for offset in offsets:
            distance = (offset - fraction) * cutoff
            sinc = sin(pi * distance) / (pi * distance) if distance else 1.0
            window = (1 + cos(pi * distance / params.lobes)) / 2
            weights.append(sinc * window if abs(distance) < params.lobes else 0.0)
        total = sum(weights)
        kernels.append([weight / total for weight in weights])
    # Continue the sustain loop into the filter's look-ahead; prepend silence at onset.
    padded = [0.0] * radius + list(sample.pcm[: sample.loop_end])
    for i in range(2 * radius):
        padded.append(sample.pcm[sample.loop_start + i % (sample.loop_end - sample.loop_start)])
    loop_start = round(sample.loop_start / step)
    loop_end = ceil(sample.loop_end / step)
    result = []
    for i in range(min(frames, loop_end)):
        position = i * step
        integer = int(position)
        phase = round((position - integer) * params.phases)
        if phase == params.phases:
            integer += 1
            phase = 0
        begin = integer + 1  # The first tap is -radius + 1, plus the left padding.
        value = sum(
            pcm * weight
            for pcm, weight in zip(padded[begin : begin + 2 * radius], kernels[phase], strict=True)
        )
        result.append(value)
    return _Sample(tuple(result), loop_start, loop_end)


class HarmonicaSampler:
    """Per-export sampler/cache for the bundled instrument; no downloads or audio extras."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self._params = _SamplerParams()
        self._root = files("harptab").joinpath("assets").joinpath("harmonica")
        bank = json.loads(self._root.joinpath("bank.json").read_text(encoding="utf-8"))
        self._source_rate: int = bank["sample_rate"]
        self._regions: list[dict[str, int | str]] = bank["regions"]
        self._sources: dict[int, _Sample] = {}
        self._pitched: dict[int, _Sample] = {}

    def _prepare(self, pitch: int, frames: int) -> _Sample:
        cached = self._pitched.get(pitch)
        if cached is not None and (len(cached.pcm) >= frames or len(cached.pcm) >= cached.loop_end):
            return cached
        region = next(r for r in self._regions if int(r["low"]) <= pitch <= int(r["high"]))
        root_pitch = int(region["root_pitch"])
        if root_pitch not in self._sources:
            data = self._root.joinpath(str(region["file"])).read_bytes()
            with wave.open(BytesIO(data)) as source:
                if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (
                    1,
                    2,
                    self._source_rate,
                ):
                    raise ValueError("invalid packaged harmonica sample format")
                pcm = array("h", source.readframes(source.getnframes()))
            if sys.byteorder != "little":
                pcm.byteswap()
            start, end = int(region["loop_start"]), int(region["loop_end"])
            if not 0 <= start < end <= len(pcm):
                raise ValueError("invalid packaged harmonica sustain loop")
            self._sources[root_pitch] = _Sample(tuple(pcm), start, end)
        step = self._source_rate / self.sample_rate * 2 ** ((pitch - root_pitch) / 12)
        prepared = _resample(self._sources[root_pitch], step, frames, self._params)
        self._pitched[pitch] = prepared
        return prepared

    def render(self, pitch: int, frames: int, amplitude: float, fade: float) -> array[int]:
        """Render a MIDI pitch for exactly ``frames`` samples, including an internal release."""
        if frames <= 0:
            return array("h")
        sample = self._prepare(pitch, frames)
        peak = max(abs(value) for value in sample.pcm) or 1
        attack = max(1, min(frames // 2, round(fade * self.sample_rate)))
        release = max(
            1, min(frames // 2, round(max(fade, self._params.release) * self.sample_rate))
        )
        result = array("h")
        for i in range(frames):
            position = i
            if position >= sample.loop_end:
                position = sample.loop_start + (position - sample.loop_end) % (
                    sample.loop_end - sample.loop_start
                )
            envelope = min(1.0, i / attack, (frames - 1 - i) / release)
            result.append(round(32767 * amplitude * envelope * sample.pcm[position] / peak))
        return result
