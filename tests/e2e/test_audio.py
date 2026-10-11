import json
from pathlib import Path

import pytest

from harptab.cli import main
from harptab.models import Melody
from harptab.pipeline import load_melody

sf = pytest.importorskip("soundfile")
pytest.importorskip("librosa")
pytestmark = pytest.mark.audio


def test_audio_cli_and_editable_intermediate(
    melody_fixture: tuple[Path, Melody],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from eval.synth import synthesize

    _, melody = melody_fixture
    signal, _ = synthesize(melody)
    wav = tmp_path / "melody.wav"
    sf.write(wav, signal, 22050)
    intermediate = tmp_path / "melody.json"
    assert main(["transcribe", str(wav), "--no-separate", "-o", str(intermediate)]) == 0
    assert [n.pitch for n in load_melody(intermediate).notes] == [n.pitch for n in melody.notes]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Tracking pitch" in captured.err
    assert main([str(wav), "--no-separate", "--harps", "C", "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data["arrangement"]["actions"]) == len(melody.notes)
    assert data["arrangement"]["transpose"] == 0


def test_silence_transcribes_to_empty_melody(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import numpy as np

    path = tmp_path / "silent.wav"
    sf.write(path, np.zeros(2205), 22050)
    assert main(["transcribe", str(path), "--no-separate"]) == 0
    assert json.loads(capsys.readouterr().out)["notes"] == []
    assert main([str(path), "--no-separate"]) == 2
    assert "no melody notes" in capsys.readouterr().err
