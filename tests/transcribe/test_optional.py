import builtins
from pathlib import Path

import pytest

from harptab.transcribe.load import load_audio


def test_missing_audio_extra_has_install_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "fake.wav"
    path.touch()
    original = builtins.__import__

    def without_audio(name: str, *args: object, **kwargs: object) -> object:
        if name in ("numpy", "librosa", "soundfile"):
            raise ImportError("simulated missing audio extra")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_audio)
    with pytest.raises(ImportError, match=r"harptab\[audio\]"):
        load_audio(path)
