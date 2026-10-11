"""Optional audio decoding, mono conversion and resampling."""

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


def load_audio(path: str | Path, sr: int = 22050) -> "NDArray[np.float32]":
    """Decode a file to a mono float32 array at ``sr`` Hz; unsupported codecs use ffmpeg."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"audio file does not exist: {path}")
    if type(sr) is not int or sr <= 0:
        raise ValueError("sample rate must be a positive integer in Hz")
    try:
        import librosa
        import numpy as np
        import soundfile as sf
    except ImportError as error:
        raise ImportError("Audio input requires: pip install 'harptab[audio]'") from error
    try:
        samples, native_sr = sf.read(str(path), dtype="float32", always_2d=True)
    except (RuntimeError, sf.LibsndfileError):
        executable = shutil.which("ffmpeg")
        if executable is None:
            raise ValueError(
                f"Cannot decode {path.name}. Install ffmpeg for this codec, "
                "or convert the file to WAV/FLAC; also check that the file is valid."
            ) from None
        decoded = subprocess.run(
            [
                executable,
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(path.resolve()),
                "-f",
                "f32le",
                "-ac",
                "1",
                "-ar",
                str(sr),
                "pipe:1",
            ],
            capture_output=True,
            check=False,
        )
        if decoded.returncode:
            detail = decoded.stderr.decode("utf-8", errors="replace").strip()
            raise ValueError(f"ffmpeg could not decode {path.name}: {detail}") from None
        audio = np.frombuffer(decoded.stdout, dtype="<f4").astype(np.float32, copy=True)
    else:
        audio = samples.mean(axis=1, dtype=np.float32)
        if native_sr != sr and len(audio):
            audio = librosa.resample(audio, orig_sr=native_sr, target_sr=sr)
    if not len(audio):
        raise ValueError("audio file contains no samples")
    if not np.isfinite(audio).all():
        raise ValueError("audio samples must be finite")
    return cast("NDArray[np.float32]", np.ascontiguousarray(audio, dtype=np.float32))
