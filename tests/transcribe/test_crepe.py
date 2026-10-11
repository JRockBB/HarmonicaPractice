import builtins
import json
import os
from importlib import import_module
from pathlib import Path

import pytest

from harptab.transcribe.crepe import CrepeParams, CrepeTracker
from harptab.transcribe.pitch import PyinParams, PyinTracker, get_tracker


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sample_rate": 22050},
        {"fmin": 0},
        {"fmax": 2100},
        {"fmax": float("nan")},
        {"hop_length": 0},
        {"hop_length": 2048},
        {"batch_size": False},
        {"transition_width": 0},
        {"median_frames": 2},
        {"min_periodicity": -0.1},
        {"model": "medium"},
        {"device": "mps"},
        {"silence_rms": -1},
        {"relative_silence": 1},
    ],
)
def test_invalid_crepe_settings(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        CrepeParams(**kwargs)


def test_tracker_factory_validates_backend_parameter_pairing() -> None:
    assert isinstance(get_tracker("crepe"), CrepeTracker)
    assert isinstance(get_tracker(), PyinTracker)
    with pytest.raises(ValueError, match="requires CrepeParams"):
        get_tracker("crepe", PyinParams())
    with pytest.raises(ValueError, match="requires PyinParams"):
        get_tracker("pyin", CrepeParams())


def test_missing_crepe_extra_has_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    original = builtins.__import__

    def without_extra(name: str, *args: object, **kwargs: object) -> object:
        if name in ("numpy", "torch", "torchcrepe", "librosa"):
            raise ImportError("simulated unavailable extra")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_extra)
    with pytest.raises(ImportError, match=r"harptab\[crepe\]"):
        CrepeTracker().track([0.1], 16000)


@pytest.fixture
def numerical() -> object:
    np = pytest.importorskip("numpy")
    pytest.importorskip("torchcrepe")
    return np


@pytest.mark.audio
def test_silence_empty_and_invalid_input(numerical: object) -> None:
    np = numerical
    tracker = CrepeTracker()
    assert tracker.track([], 16000).times == []
    silent = tracker.track(np.zeros(1601, dtype=np.float32), 16000)
    assert len(silent.times) == 11
    assert all(value == 0 for value in silent.voiced_prob)
    assert np.isnan(silent.f0_hz).all()
    assert tracker._model is None
    for audio in ([[0.1]], [np.nan], [np.inf]):
        with pytest.raises(ValueError, match="mono signal"):
            tracker.track(audio, 16000)
    with pytest.raises(ValueError, match="positive integer"):
        tracker.track([0.1], 0)


@pytest.mark.audio
def test_real_model_preserves_pitch_rate_rests_and_batch_boundaries(numerical: object) -> None:
    np = numerical
    torch = import_module("torch")
    torchcrepe = import_module("torchcrepe")
    before = getattr(torchcrepe.infer, "model", None)
    before_grad = torch.is_grad_enabled()
    sr = 22050
    time = np.arange(round(0.45 * sr)) / sr
    tone = (0.3 * np.sin(2 * np.pi * 440 * time)).astype(np.float32)
    audio = np.concatenate((tone, np.zeros(round(0.15 * sr), dtype=np.float32), tone))
    tracker = CrepeTracker(CrepeParams(batch_size=32, device="cpu"))
    first = tracker.track(audio, sr)
    model = tracker._model
    tracker.params = CrepeParams(batch_size=64, device="cpu")
    second = tracker.track(audio, sr)
    assert tracker._model is model
    assert getattr(torchcrepe.infer, "model", None) is before
    np.testing.assert_allclose(first.f0_hz, second.f0_hz, equal_nan=True)
    np.testing.assert_allclose(first.voiced_prob, second.voiced_prob, rtol=1e-4, atol=1e-5)
    times = np.asarray(first.times)
    f0 = np.asarray(first.f0_hz)
    interior = ((times > 0.1) & (times < 0.4)) | ((times > 0.7) & (times < 1))
    assert np.isfinite(f0[interior]).mean() >= 0.95
    assert np.mean(np.abs(1200 * np.log2(f0[interior] / 440)) <= 50) >= 0.95
    assert np.isnan(f0[(times > 0.48) & (times < 0.57)]).all()
    assert times[-1] < len(audio) / sr
    assert times[1] - times[0] == pytest.approx(0.01)
    assert torch.is_grad_enabled() == before_grad


@pytest.mark.audio
def test_crepe_cli_excerpt_returns_editable_notes(
    numerical: object, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from harptab.cli import main

    np = numerical
    sf = pytest.importorskip("soundfile")
    path = tmp_path / "tone.wav"
    audio = 0.3 * np.sin(2 * np.pi * 440 * np.arange(22050) / 22050)
    sf.write(path, audio, 22050, subtype="FLOAT")
    assert (
        main(
            [
                "transcribe",
                str(path),
                "--no-separate",
                "--pitch-backend",
                "crepe",
                "--start",
                "0.2",
                "--duration",
                "0.6",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    notes = json.loads(captured.out)["notes"]
    assert [note["pitch"] for note in notes] == [69]
    assert notes[0]["start"] >= 0.2
    assert notes[0]["start"] + notes[0]["duration"] <= 0.8 + 1e-9
    assert "Tracking pitch with CREPE..." in captured.err


@pytest.mark.audio
@pytest.mark.separation
@pytest.mark.skipif(
    os.environ.get("HARPTAB_TEST_DEMUCS") != "1", reason="explicit model download opt-in"
)
def test_demucs_and_crepe_work_together_on_an_excerpt(
    numerical: object, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from harptab.cli import main

    np = numerical
    sf = pytest.importorskip("soundfile")
    pytest.importorskip("demucs_infer")
    path = tmp_path / "tone.wav"
    sf.write(path, 0.3 * np.sin(2 * np.pi * 440 * np.arange(22050) / 22050), 22050, subtype="FLOAT")
    cache = os.environ.get("HARPTAB_DEMUCS_CACHE", str(tmp_path / "cache"))
    assert (
        main(
            [
                "transcribe",
                str(path),
                "--pitch-backend",
                "crepe",
                "--stem",
                "other",
                "--device",
                "cpu",
                "--cache-dir",
                cache,
                "--start",
                "0.2",
                "--duration",
                "0.6",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    notes = json.loads(captured.out)["notes"]
    assert [note["pitch"] for note in notes] == [69]
    assert notes[0]["start"] >= 0.2
    assert notes[0]["start"] + notes[0]["duration"] <= 0.8 + 1e-9
    assert "Tracking pitch with CREPE..." in captured.err
    assert "other" in captured.err
