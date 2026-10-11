"""Optional CREPE inference with tracker-owned weights and deterministic decoding."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.resources import as_file, files
from math import isfinite
from typing import Any

from harptab.transcribe.pitch import PitchTrack

# Fixed encoding of the pretrained network's first pitch bin, relative to 10 Hz.
_BIN_ZERO_CENTS = 1997.3794084376191


@dataclass(frozen=True)
class CrepeParams:
    sample_rate: int = 16000  # Native CREPE input rate, Hz.
    hop_length: int = 160  # Frame spacing in native-rate samples (10 ms).
    fmin: float = 65.406391  # Lower pitch bound, C2 in Hz.
    fmax: float = 2000.0  # Upper pitch bound; CREPE supports at most 2006 Hz.
    model: str = "full"  # Pretrained capacity: full or tiny.
    device: str = "auto"  # CUDA if available, otherwise CPU.
    batch_size: int = 128  # Maximum neural inference frames per batch.
    transition_width: int = 12  # Viterbi transition width in 20-cent pitch bins.
    min_periodicity: float = 0.21  # Reject low-periodicity frames before segmentation.
    median_frames: int = 3  # Odd smoothing window for periodicity.
    silence_rms: float = 0.0001  # Absolute short-window RMS silence gate.
    relative_silence: float = 0.03  # Silence gate as a fraction of peak RMS.

    def __post_init__(self) -> None:
        if type(self.sample_rate) is not int or self.sample_rate != 16000:
            raise ValueError("CREPE sample_rate must be its native 16000 Hz")
        if not (isfinite(self.fmin) and isfinite(self.fmax) and 0 < self.fmin < self.fmax <= 2006):
            raise ValueError("CREPE frequency bounds must satisfy 0 < fmin < fmax <= 2006 Hz")
        for name in ("hop_length", "batch_size", "transition_width", "median_frames"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"CREPE {name} must be a positive integer")
        if self.hop_length > 1024 or self.median_frames % 2 != 1:
            raise ValueError("CREPE hop_length must be <=1024 and median_frames must be odd")
        if self.model not in ("tiny", "full"):
            raise ValueError("CREPE model must be tiny or full")
        if not re.fullmatch(r"auto|cpu|cuda(?::[0-9]+)?", self.device):
            raise ValueError("CREPE device must be auto, cpu, cuda or cuda:N")
        if not isfinite(self.min_periodicity) or not 0 <= self.min_periodicity <= 1:
            raise ValueError("CREPE min_periodicity must be in 0..1")
        if not isfinite(self.silence_rms) or self.silence_rms < 0:
            raise ValueError("CREPE silence_rms must be finite and nonnegative")
        if not isfinite(self.relative_silence) or not 0 <= self.relative_silence < 1:
            raise ValueError("CREPE relative_silence must be in [0, 1)")


class CrepeTracker:
    """Track mono audio with CREPE; model state belongs to this reusable instance.

    Confidence is raw model periodicity, not a calibrated probability of the note
    being correct. Segmentation's confidence threshold still applies separately.
    """

    def __init__(self, params: CrepeParams | None = None) -> None:
        self.params = params or CrepeParams()
        self._model: Any = None
        self._device: str | None = None
        self._capacity: str | None = None

    def track(self, audio: Sequence[float], sr: int) -> PitchTrack:
        """Return centered frame times in seconds, Hz and periodicity, with NaN for silence."""
        if type(sr) is not int or sr <= 0:
            raise ValueError("sample rate must be a positive integer in Hz")
        try:
            import librosa
            import numpy as np
            import torch
            import torchcrepe
        except ImportError as error:
            raise ImportError("CREPE tracking requires: pip install 'harptab[crepe]'") from error
        p = self.params
        samples = np.asarray(audio, dtype=np.float32)
        if samples.ndim != 1 or not np.isfinite(samples).all():
            raise ValueError("pitch tracking requires a finite one-dimensional mono signal")
        if not len(samples):
            return PitchTrack([], [], [])
        duration = len(samples) / sr
        if sr != p.sample_rate:
            samples = librosa.resample(samples, orig_sr=sr, target_sr=p.sample_rate)
        times = np.arange(0, len(samples), p.hop_length, dtype=float) / p.sample_rate
        times = times[times < duration]
        if float(np.max(np.abs(samples))) <= p.silence_rms:
            return PitchTrack(times.tolist(), [float("nan")] * len(times), [0.0] * len(times))
        device = p.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise ValueError("CUDA is unavailable for CREPE; use CrepeParams(device='cpu')")
        try:
            with torch.inference_mode():
                if self._model is None or self._device != device or self._capacity != p.model:
                    # Avoid torchcrepe.predict's mutable process-global model cache.
                    model = torchcrepe.Crepe(p.model)
                    weights = files("torchcrepe").joinpath("assets", f"{p.model}.pth")
                    with as_file(weights) as path:
                        model.load_state_dict(
                            torch.load(path, map_location="cpu", weights_only=True)
                        )
                    self._model = model.to(device).eval()
                    self._device = device
                    self._capacity = p.model
                waveform = torch.from_numpy(np.ascontiguousarray(samples))[None, :]
                batches = [
                    self._model(frames).cpu()
                    for frames in torchcrepe.preprocess(
                        waveform, p.sample_rate, p.hop_length, p.batch_size, device, pad=True
                    )
                ]
                # Decode once across batch boundaries, so batch size is only a memory setting.
                activations = torch.cat(batches, dim=0)[: len(times)].numpy().T
        except (OSError, RuntimeError) as error:
            raise ValueError(f"CREPE inference failed: {error}") from error
        if not np.isfinite(activations).all():
            raise ValueError("CREPE returned non-finite activations")
        bins = np.arange(activations.shape[0])
        frequencies = 10 * 2 ** ((bins * torchcrepe.CENTS_PER_BIN + _BIN_ZERO_CENTS) / 1200)
        allowed = (frequencies >= p.fmin) & (frequencies <= p.fmax)
        if not np.any(allowed):
            raise ValueError("CREPE frequency range contains no model pitch bins")
        logits = np.where(allowed[:, None], activations, -np.inf)
        probabilities = np.exp(logits - np.max(logits, axis=0))
        probabilities /= probabilities.sum(axis=0)
        transitions = np.maximum(p.transition_width - np.abs(bins[:, None] - bins[None, :]), 0)
        transitions = transitions / transitions.sum(axis=1, keepdims=True)
        chosen = librosa.sequence.viterbi(probabilities, transitions)
        f0 = frequencies[chosen]
        periodicity = activations[chosen, np.arange(len(times))]
        radius = p.median_frames // 2
        padded = np.pad(periodicity, (radius, radius), mode="edge")
        periodicity = np.median(
            np.lib.stride_tricks.sliding_window_view(padded, p.median_frames), axis=1
        )
        rms = librosa.feature.rms(
            y=samples, frame_length=2 * p.hop_length, hop_length=p.hop_length, center=True
        )[0][: len(times)]
        threshold = max(p.silence_rms, p.relative_silence * float(np.max(rms)))
        valid = (rms > threshold) & (periodicity >= p.min_periodicity)
        return PitchTrack(
            times.tolist(),
            np.where(valid, f0, np.nan).tolist(),
            np.where(valid, np.clip(periodicity, 0, 1), 0).tolist(),
        )
