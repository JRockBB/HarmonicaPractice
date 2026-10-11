"""Optional Demucs inference with an explicit, content-addressed stem cache."""

import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, cast
from zipfile import BadZipFile

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

STEMS = ("vocals", "other", "bass", "drums")
MODELS = ("htdemucs", "htdemucs_ft")
_INSTALL = (
    "Source separation requires: pip install 'harptab[separation]'. "
    "For a solo source, use --no-separate."
)
_CACHE_SCHEMA = 1


@dataclass(frozen=True)
class SeparationParams:
    """Inference and cache options; sample rates elsewhere are in Hz."""

    model: str = "htdemucs"  # Official four-stem checkpoint family.
    device: str = "auto"  # CUDA when available, otherwise CPU.
    shifts: int = 0  # Disable random time-shift averaging for reproducible inference.
    overlap: float = 0.25  # Fraction of neighboring chunks to crossfade.
    segment: float = 7.0  # Chunk duration, seconds; hybrid transformers allow up to 7.8.
    cache_dir: Path | None = None  # None selects the platform's harptab user cache.
    use_cache: bool = True  # Reuse/write stems; downloaded model weights remain cached.

    def __post_init__(self) -> None:
        if self.model not in MODELS:
            raise ValueError(f"unsupported separation model: {self.model}")
        if not re.fullmatch(r"auto|cpu|cuda(?::[0-9]+)?", self.device):
            raise ValueError("separation device must be auto, cpu, cuda or cuda:N")
        if type(self.shifts) is not int or self.shifts < 0:
            raise ValueError("separation shifts must be a nonnegative integer")
        if not math.isfinite(self.overlap) or not 0 <= self.overlap < 1:
            raise ValueError("separation overlap must be in [0, 1)")
        if not math.isfinite(self.segment) or not 0 < self.segment <= 7.8:
            raise ValueError("separation segment must be in (0, 7.8] seconds")


def file_digest(path: str | Path) -> str:
    """Return the SHA-256 of a source file without loading it all into memory."""
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _versions() -> dict[str, str]:
    try:
        return {name: version(name) for name in ("demucs-infer", "torch", "librosa")}
    except PackageNotFoundError as error:
        raise ImportError(_INSTALL) from error


def _cache_root(params: SeparationParams) -> Path:
    if params.cache_dir is not None:
        return Path(params.cache_dir)
    try:
        from platformdirs import user_cache_dir
    except ImportError as error:
        raise ImportError(_INSTALL) from error
    return Path(user_cache_dir("harptab", appauthor=False))


def _read_cache(path: Path, key: str, size: int) -> "NDArray[np.float32] | None":
    import numpy as np

    try:
        with np.load(path, allow_pickle=False) as cached:
            audio = cached["audio"]
            if (
                str(cached["key"].item()) == key
                and audio.shape == (size,)
                and audio.dtype == np.float32
                and np.isfinite(audio).all()
            ):
                return cast("NDArray[np.float32]", audio)
    except (OSError, ValueError, EOFError, KeyError, TypeError, BadZipFile):
        pass  # A stale or interrupted cache must not prevent fresh inference.
    return None


def _write_cache(path: Path, key: str, audio: "NDArray[np.float32]") -> None:
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as out:
            temporary = Path(out.name)
            np.savez(out, key=key, audio=audio)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _run_demucs(
    audio: "NDArray[np.float32]", sr: int, stem: str, params: SeparationParams, root: Path
) -> "NDArray[np.float32]":
    try:
        import librosa
        import numpy as np
        import torch
        from demucs_infer import DemucsSession
    except ImportError as error:
        raise ImportError(_INSTALL) from error
    device = params.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device.startswith("cuda") and not torch.cuda.is_available():
        raise ValueError("CUDA is unavailable in this PyTorch installation; use --device cpu")
    # The loading contract is mono; Demucs expects two channels even at its native rate.
    stereo = torch.from_numpy(np.stack((audio, audio)))
    try:
        with (
            torch.inference_mode(),
            DemucsSession(
                model=params.model,
                cache_dir=root / "models",
                device=device,
                shifts=params.shifts,
                overlap=params.overlap,
                segment=params.segment,
                progress=False,
            ) as session,
        ):
            _, stems = session.infer(stereo, sample_rate=sr)
            result = stems[stem].detach().cpu().numpy().mean(axis=0)
            native_sr = session.samplerate
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(
            f"Demucs separation failed: {error}. Check model download access, cache space "
            "and the selected device; --no-separate bypasses separation for solo sources."
        ) from error
    if native_sr != sr:
        result = librosa.resample(result, orig_sr=native_sr, target_sr=sr)
    # Resamplers can round the sample count up; maintain the stage's exact length contract.
    result = np.pad(result[: len(audio)], (0, max(0, len(audio) - len(result))))
    return cast("NDArray[np.float32]", np.ascontiguousarray(result, dtype=np.float32))


def separate(
    audio: "Sequence[float] | NDArray[np.float32]",
    sr: int,
    stem: str = "vocals",
    *,
    params: SeparationParams | None = None,
    source_hash: str | None = None,
    progress: Callable[[str], None] | None = None,
) -> "NDArray[np.float32]":
    """Isolate a stem, returning mono float32 at the original rate and sample count.

    ``source_hash`` optionally identifies the original file (SHA-256). The decoded
    samples, sample rate, model, stem and inference settings also enter the cache key.
    Cache hits never import Torch or load a model. First inference downloads weights.
    """
    p = params or SeparationParams()
    if type(sr) is not int or sr <= 0:
        raise ValueError("sample rate must be a positive integer in Hz")
    if stem not in STEMS:
        raise ValueError(f"unsupported stem {stem!r}; choose from {', '.join(STEMS)}")
    if source_hash is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", source_hash):
        raise ValueError("source_hash must be a SHA-256 hex digest")
    try:
        import numpy as np
    except ImportError as error:
        raise ImportError(_INSTALL) from error
    samples = np.ascontiguousarray(audio, dtype=np.float32)
    if samples.ndim != 1 or not len(samples) or not np.isfinite(samples).all():
        raise ValueError("separation audio must be a nonempty, finite mono array")
    if not np.any(samples):
        return cast("NDArray[np.float32]", samples.copy())
    metadata = {
        "schema": _CACHE_SCHEMA,
        "versions": _versions(),
        "source": source_hash.lower() if source_hash else None,
        "audio": hashlib.sha256(samples.astype("<f4", copy=False).tobytes()).hexdigest(),
        "sr": sr,
        "model": p.model,
        "stem": stem,
        "device": p.device,
        "shifts": p.shifts,
        "overlap": p.overlap,
        "segment": p.segment,
    }
    key = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
    root = _cache_root(p)
    path = root / "stems" / f"{key}.npz"
    if p.use_cache:
        cached = _read_cache(path, key, len(samples))
        if cached is not None:
            if progress:
                progress(f"Using cached {stem} stem...")
            return cached
    if progress:
        progress(f"Separating {stem} with {p.model} ({p.device}); first use downloads weights...")
    result = _run_demucs(samples, sr, stem, p, root)
    if result.shape != samples.shape or result.dtype != np.float32 or not np.isfinite(result).all():
        raise ValueError("Demucs returned invalid audio")
    if p.use_cache:
        _write_cache(path, key, result)
    return result
