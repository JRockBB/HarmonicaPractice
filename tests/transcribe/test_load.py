import subprocess
from pathlib import Path

import pytest

from harptab.transcribe.load import load_audio

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")
pytestmark = pytest.mark.audio


@pytest.mark.parametrize("suffix", [".wav", ".flac"])
def test_decode_stereo_and_resample(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / ("stereo" + suffix)
    source = np.column_stack((np.full(16000, 0.25), np.full(16000, 0.75)))
    sf.write(path, source, 16000)
    samples = load_audio(path, 22050)
    assert samples.dtype == np.float32
    assert samples.shape == (22050,)
    assert float(np.median(samples)) == pytest.approx(0.5, abs=0.001)


def test_bad_file_and_missing_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "invalid.m4a"
    path.write_bytes(b"invalid audio")
    monkeypatch.setattr("harptab.transcribe.load.shutil.which", lambda _: None)
    with pytest.raises(ValueError, match="Install ffmpeg"):
        load_audio(path)
    with pytest.raises(FileNotFoundError):
        load_audio(tmp_path / "absent.wav")
    with pytest.raises(ValueError, match="sample rate"):
        load_audio(path, 0)


def test_ffmpeg_fallback_arguments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "input with spaces.m4a"
    path.write_bytes(b"fake container")
    monkeypatch.setattr("harptab.transcribe.load.shutil.which", lambda _: "ffmpeg-test")
    samples = np.array([0.25, -0.25], dtype="<f4")

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert command[0] == "ffmpeg-test"
        assert command[command.index("-i") + 1] == str(path.resolve())
        assert command[-1] == "pipe:1"
        assert "shell" not in kwargs
        return subprocess.CompletedProcess(command, 0, samples.tobytes(), b"")

    monkeypatch.setattr("harptab.transcribe.load.subprocess.run", run)
    assert load_audio(path).tolist() == samples.tolist()


def test_empty_and_nonfinite_files_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.wav"
    sf.write(path, np.array([], dtype=np.float32), 22050)
    with pytest.raises(ValueError, match="no samples"):
        load_audio(path)
    sf.write(path, np.array([np.nan, 0.1], dtype=np.float32), 22050, subtype="FLOAT")
    with pytest.raises(ValueError, match="finite"):
        load_audio(path)
