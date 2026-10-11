import builtins
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from importlib import import_module
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

from harptab.transcribe.separate import SeparationParams, file_digest, separate

adapter = import_module("harptab.transcribe.separate")


@pytest.mark.parametrize(
    "options",
    [
        {"model": "unknown"},
        {"device": "mps"},
        {"device": "cuda:-1"},
        {"shifts": -1},
        {"shifts": True},
        {"overlap": 1},
        {"overlap": float("nan")},
        {"segment": 0},
        {"segment": 8},
    ],
)
def test_invalid_settings(options: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        SeparationParams(**options)


@pytest.mark.parametrize(
    "options", [{"sr": 0}, {"sr": True}, {"stem": "lead"}, {"source_hash": "x"}]
)
def test_invalid_arguments_without_importing_audio(options: dict[str, object]) -> None:
    kwargs = {"sr": 22050, **options}
    with pytest.raises(ValueError):
        separate([0.1], **kwargs)


def test_file_hash_tracks_contents(tmp_path: Path) -> None:
    path = tmp_path / "source.wav"
    path.write_bytes(b"first")
    assert file_digest(path) == hashlib.sha256(b"first").hexdigest()
    path.write_bytes(b"second")
    assert file_digest(path) == hashlib.sha256(b"second").hexdigest()


def test_missing_separation_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    original = builtins.__import__

    def blocked(name: str, *args: object, **kwargs: object) -> object:
        if name == "numpy":
            raise ImportError("test missing dependency")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(ImportError, match=r"harptab\[separation\].*--no-separate"):
        separate([0.1], 22050)


def test_missing_distribution_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(adapter, "version", missing)
    with pytest.raises(ImportError, match=r"harptab\[separation\]"):
        adapter._versions()


@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, ...]]:
    np = pytest.importorskip("numpy")
    calls: list[tuple[object, ...]] = []

    def run(audio: object, *args: object) -> object:
        calls.append(args)
        return np.asarray(audio, dtype=np.float32) * 0.5

    monkeypatch.setattr(adapter, "_run_demucs", run)
    monkeypatch.setattr(adapter, "_versions", lambda: {"demucs-infer": "test"})
    return calls


@pytest.mark.audio
def test_cache_hit_never_imports_torch_or_runs_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_backend: list[tuple[object, ...]]
) -> None:
    np = pytest.importorskip("numpy")
    p = SeparationParams(cache_dir=tmp_path)
    messages: list[str] = []
    expected = separate([0.1, -0.2, 0.3], 22050, params=p)
    original = builtins.__import__

    def blocked(name: str, *args: object, **kwargs: object) -> object:
        if name.split(".")[0] in ("torch", "demucs_infer"):
            pytest.fail("cache hit imported inference backend")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    actual = separate([0.1, -0.2, 0.3], 22050, params=p, progress=messages.append)
    np.testing.assert_array_equal(actual, expected)
    assert len(fake_backend) == 1
    assert messages == ["Using cached vocals stem..."]
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.audio
@pytest.mark.parametrize(
    "change",
    [
        "audio",
        "sr",
        "stem",
        "source_hash",
        "model",
        "device",
        "shifts",
        "overlap",
        "segment",
        "version",
    ],
)
def test_cache_invalidates_on_every_inference_input(
    change: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_backend: list[tuple[object, ...]],
) -> None:
    p = SeparationParams(cache_dir=tmp_path)
    audio = [0.1, 0.2, 0.3]
    kwargs = {"sr": 22050, "stem": "vocals", "source_hash": "a" * 64}
    separate(audio, params=p, **kwargs)
    if change == "audio":
        audio[-1] = 0.4
    elif change in kwargs:
        kwargs[change] = {"sr": 44100, "stem": "other", "source_hash": "b" * 64}[change]
    elif change == "version":
        monkeypatch.setattr(adapter, "_versions", lambda: {"demucs-infer": "next"})
    else:
        value = {
            "model": "htdemucs_ft",
            "device": "cpu",
            "shifts": 1,
            "overlap": 0.5,
            "segment": 5,
        }[change]
        p = replace(p, **{change: value})
    separate(audio, params=p, **kwargs)
    assert len(fake_backend) == 2


@pytest.mark.audio
@pytest.mark.parametrize(
    "damage", ["truncated", "wrong_shape", "wrong_key", "nan", "wrong_dtype", "npy"]
)
def test_corrupted_cache_recomputes(
    damage: str, tmp_path: Path, fake_backend: list[tuple[object, ...]]
) -> None:
    np = pytest.importorskip("numpy")
    p = SeparationParams(cache_dir=tmp_path)
    expected = separate([0.1, 0.2], 22050, params=p)
    cached = next(tmp_path.rglob("*.npz"))
    if damage == "truncated":
        cached.write_bytes(b"PK\x03")
    elif damage == "npy":
        with cached.open("wb") as output:
            np.save(output, expected)
    else:
        audio = expected.copy()
        key = cached.stem
        if damage == "wrong_shape":
            audio = audio[:1]
        elif damage == "wrong_key":
            key = "wrong"
        elif damage == "nan":
            audio[0] = float("nan")
        else:
            audio = audio.astype(np.float64)
        np.savez(cached, audio=audio, key=key)
    actual = separate([0.1, 0.2], 22050, params=p)
    np.testing.assert_array_equal(actual, expected)
    assert len(fake_backend) == 2


@pytest.mark.audio
def test_cache_bypass_and_write_failure_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_backend: list[tuple[object, ...]]
) -> None:
    p = SeparationParams(cache_dir=tmp_path, use_cache=False)
    for _ in range(2):
        separate([0.1, 0.2], 22050, params=p)
    assert len(fake_backend) == 2
    assert not list(tmp_path.rglob("*.npz"))

    def denied(*args: object) -> None:
        raise PermissionError("test cannot replace")

    monkeypatch.setattr(adapter.os, "replace", denied)
    with pytest.raises(PermissionError):
        separate([0.1, 0.2], 22050, params=replace(p, use_cache=True))
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.audio
@pytest.mark.parametrize("audio", [[], [[0.1, 0.2]], [float("nan")], [float("inf")]])
def test_invalid_waveforms(audio: object, fake_backend: list[tuple[object, ...]]) -> None:
    with pytest.raises(ValueError, match="nonempty, finite mono"):
        separate(audio, 22050)
    assert not fake_backend


@pytest.mark.audio
def test_silence_needs_no_model(tmp_path: Path, fake_backend: list[tuple[object, ...]]) -> None:
    np = pytest.importorskip("numpy")
    result = separate([0.0] * 10, 22050, params=SeparationParams(cache_dir=tmp_path))
    assert result.dtype == np.float32
    assert result.shape == (10,)
    assert not result.any()
    assert not fake_backend


@pytest.mark.audio
@pytest.mark.separation
@pytest.mark.skipif(
    os.environ.get("HARPTAB_TEST_DEMUCS") != "1", reason="explicit model download opt-in"
)
def test_real_cpu_model_preserves_rate_length_and_cache(tmp_path: Path) -> None:
    np = pytest.importorskip("numpy")
    pytest.importorskip("demucs_infer")
    audio = (0.3 * np.sin(2 * np.pi * 440 * np.arange(22050) / 22050)).astype(np.float32)
    cache_root = Path(os.environ.get("HARPTAB_DEMUCS_CACHE", str(tmp_path)))
    params = SeparationParams(device="cpu", cache_dir=cache_root)
    actual = separate(audio, 22050, "other", params=params)
    assert actual.shape == audio.shape
    assert actual.dtype == np.float32
    assert np.isfinite(actual).all()
    assert np.max(np.abs(actual)) > 0
    # A 440 Hz input must remain at 440 Hz after both resampling directions.
    peak_hz = np.argmax(np.abs(np.fft.rfft(actual))) * 22050 / len(actual)
    assert peak_hz == pytest.approx(440, abs=2)
    np.testing.assert_array_equal(actual, separate(audio, 22050, "other", params=params))


@pytest.mark.audio
@pytest.mark.separation
@pytest.mark.skipif(
    os.environ.get("HARPTAB_TEST_DEMUCS") != "1", reason="explicit model download opt-in"
)
def test_real_separation_cli_keeps_json_stdout_clean(tmp_path: Path) -> None:
    np = pytest.importorskip("numpy")
    sf = pytest.importorskip("soundfile")
    pytest.importorskip("demucs_infer")
    path = tmp_path / "tone.wav"
    cache_root = Path(os.environ.get("HARPTAB_DEMUCS_CACHE", str(tmp_path / "cache")))
    audio = 0.3 * np.sin(2 * np.pi * 440 * np.arange(22050) / 22050)
    sf.write(path, audio, 22050, subtype="FLOAT")
    for attempt in range(2):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "harptab",
                "transcribe",
                str(path),
                "--stem",
                "other",
                "--device",
                "cpu",
                "--cache-dir",
                str(cache_root),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        melody = json.loads(result.stdout)
        assert [note["pitch"] for note in melody["notes"]] == [69]
        assert "Tracking pitch" in result.stderr
        if attempt:
            assert "Using cached other stem" in result.stderr
