"""Pitch tracking behind an interface that can be imported without audio extras."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Protocol


@dataclass(frozen=True)
class PitchTrack:
    """Frame times in seconds, fundamental frequency in Hz, and probability in 0..1."""

    times: Sequence[float]
    f0_hz: Sequence[float]
    voiced_prob: Sequence[float]


class PitchTracker(Protocol):
    def track(self, audio: Sequence[float], sr: int) -> PitchTrack:
        """Estimate frame-level pitch from mono audio at ``sr`` samples per second."""
        ...


@dataclass(frozen=True)
class PyinParams:
    sample_rate: int = 22050  # Default decoder output sample rate, Hz.
    fmin: float = 65.406391  # Lowest tracked frequency, C2 in Hz.
    fmax: float = 2093.004522  # Highest tracked frequency, C7 in Hz.
    frame_length: int = 1024  # Analysis window in samples.
    hop_length: int = 128  # Time between frame centers in samples.
    resolution: float = 0.1  # Pitch grid spacing in semitones.
    silence_rms: float = 0.0001  # Absolute silence gate in normalized sample units.
    relative_silence: float = 0.03  # Silence gate relative to the peak short-window RMS.


class PyinTracker:
    """pYIN with centered timestamps and a short RMS gate to preserve rests."""

    def __init__(self, params: PyinParams | None = None) -> None:
        self.params = params or PyinParams()

    def track(self, audio: Sequence[float], sr: int) -> PitchTrack:
        """Track mono audio at ``sr`` Hz; unvoiced frames have NaN frequency and zero confidence."""
        p = self.params
        if type(sr) is not int or sr <= 0:
            raise ValueError("sample rate must be a positive integer in Hz")
        if not (isfinite(p.fmin) and isfinite(p.fmax) and 0 < p.fmin < p.fmax < sr / 2):
            raise ValueError("pitch frequency bounds must satisfy 0 < fmin < fmax < sr/2")
        if (
            type(p.frame_length) is not int
            or type(p.hop_length) is not int
            or p.frame_length < 2 * sr / p.fmin
            or not 0 < p.hop_length <= p.frame_length
        ):
            raise ValueError("frame_length must span two periods at fmin, with a positive hop")
        if not isfinite(p.resolution) or not 0 < p.resolution <= 1:
            raise ValueError("pitch resolution must be in (0, 1] semitones")
        if (
            not isfinite(p.silence_rms)
            or p.silence_rms < 0
            or not isfinite(p.relative_silence)
            or not 0 <= p.relative_silence < 1
        ):
            raise ValueError(
                "silence thresholds must be finite and nonnegative; relative must be <1"
            )
        try:
            import librosa
            import numpy as np
        except ImportError as error:
            raise ImportError("Pitch tracking requires: pip install 'harptab[audio]'") from error
        samples = np.asarray(audio, dtype=np.float32)
        if samples.ndim != 1 or not np.isfinite(samples).all():
            raise ValueError("pitch tracking requires a finite one-dimensional mono signal")
        if not len(samples):
            return PitchTrack([], [], [])
        # Exclude a frame centered at EOF; the final frame represents a partial hop.
        times = np.arange(0, len(samples), p.hop_length, dtype=float) / sr
        if float(np.max(np.abs(samples))) <= p.silence_rms:
            return PitchTrack(times.tolist(), [float("nan")] * len(times), [0.0] * len(times))
        padded = np.pad(samples, (0, max(0, p.frame_length - len(samples))))
        f0, voiced, probability = librosa.pyin(
            padded,
            sr=sr,
            fmin=p.fmin,
            fmax=p.fmax,
            frame_length=p.frame_length,
            hop_length=p.hop_length,
            resolution=p.resolution,
            center=True,
            fill_na=np.nan,
        )
        rms = librosa.feature.rms(
            y=padded, frame_length=2 * p.hop_length, hop_length=p.hop_length, center=True
        )[0][: len(times)]
        threshold = max(p.silence_rms, p.relative_silence * float(np.max(rms)))
        valid = voiced[: len(times)] & (rms > threshold) & np.isfinite(f0[: len(times)])
        frequencies = np.where(valid, f0[: len(times)], np.nan)
        probabilities = np.where(valid, probability[: len(times)], 0.0)
        return PitchTrack(times.tolist(), frequencies.tolist(), probabilities.tolist())


def get_tracker(backend: str = "pyin", params: PyinParams | None = None) -> PitchTracker:
    """Create a tracker; unsupported ML backends fail explicitly rather than falling back."""
    if backend != "pyin":
        raise ValueError(f"pitch backend {backend!r} is not implemented; use 'pyin'")
    return PyinTracker(params)
