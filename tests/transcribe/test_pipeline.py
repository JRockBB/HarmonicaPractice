from pathlib import Path

import pytest

from harptab.pipeline import load_melody, transcribe_audio
from harptab.transcribe.pitch import PitchTrack
from harptab.transcribe.separate import SeparationParams, file_digest


@pytest.mark.parametrize("bypass,extra", [(False, "separation"), (True, "audio")])
def test_pipeline_missing_extra_points_to_requested_mode(
    bypass: bool, extra: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*args: object) -> None:
        raise ImportError("Audio input requires: pip install 'harptab[audio]'")

    monkeypatch.setattr("harptab.transcribe.load.load_audio", missing)
    with pytest.raises(ImportError, match=rf"requires: pip install 'harptab\[{extra}\]'"):
        transcribe_audio("mix.wav", no_separate=bypass)


def test_recording_end_clips_final_frame_and_reports_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Tracker:
        def track(self, audio: object, sr: int) -> PitchTrack:
            assert len(audio) == 2535
            assert sr == 22050
            return PitchTrack([0, 0.05, 0.1], [440, 440, 440], [1, 1, 1])

    monkeypatch.setattr("harptab.transcribe.load.load_audio", lambda path, sr: [0.1] * 2535)
    monkeypatch.setattr("harptab.pipeline.get_tracker", lambda *args: Tracker())
    monkeypatch.setattr(
        "harptab.transcribe.separate.separate",
        lambda *args, **kwargs: pytest.fail("bypass separated"),
    )
    messages: list[str] = []
    melody = transcribe_audio(Path("solo.wav"), no_separate=True, progress=messages.append)
    assert len(melody.notes) == 1
    assert melody.notes[0].pitch == 69
    assert melody.notes[0].duration == pytest.approx(2535 / 22050)
    assert melody.source == "solo.wav"
    assert messages == ["Loading audio...", "Tracking pitch with pYIN...", "Segmenting notes..."]


def test_pipeline_tracks_selected_stem_and_forwards_source_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "mix.wav"
    path.write_bytes(b"source file bytes")
    original = [0.1] * 2535
    isolated = [0.2] * 2535
    config = SeparationParams(cache_dir=tmp_path, device="cpu")
    messages: list[str] = []

    def separate(audio: object, sr: int, stem: str, **kwargs: object) -> list[float]:
        assert audio is original
        assert sr == 22050
        assert stem == "other"
        assert kwargs["params"] is config
        assert kwargs["source_hash"] == file_digest(path)
        kwargs["progress"]("Using cached other stem...")
        return isolated

    class Tracker:
        def track(self, audio: object, sr: int) -> PitchTrack:
            assert audio is isolated
            return PitchTrack([0, 0.05, 0.1], [440, 440, 440], [1, 1, 1])

    monkeypatch.setattr("harptab.transcribe.load.load_audio", lambda *args: original)
    monkeypatch.setattr("harptab.transcribe.separate.separate", separate)
    monkeypatch.setattr("harptab.pipeline.get_tracker", lambda *args: Tracker())
    melody = load_melody(path, stem="other", separation_params=config, progress=messages.append)
    assert melody.notes[0].pitch == 69
    assert messages[1] == "Using cached other stem..."


def test_excerpt_preserves_recording_timestamps(monkeypatch: pytest.MonkeyPatch) -> None:
    samples = [0.1] * 22050

    class Tracker:
        def track(self, audio: object, sr: int) -> PitchTrack:
            assert len(audio) == 6615
            return PitchTrack([0, 0.1, 0.2], [440] * 3, [1] * 3)

    monkeypatch.setattr("harptab.transcribe.load.load_audio", lambda *args: samples)
    monkeypatch.setattr("harptab.pipeline.get_tracker", lambda *args: Tracker())
    melody = transcribe_audio("solo.wav", no_separate=True, start=0.7, duration=0.5)
    assert melody.notes[0].start == pytest.approx(0.7)
    assert melody.notes[0].duration == pytest.approx(0.3)


@pytest.mark.parametrize(
    "kwargs", [{"start": -1}, {"start": float("nan")}, {"duration": 0}, {"duration": float("inf")}]
)
def test_invalid_excerpt_rejected_before_loading(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="excerpt"):
        transcribe_audio("nonexistent.wav", **kwargs)


def test_empty_excerpt_and_symbolic_options_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("harptab.transcribe.load.load_audio", lambda *args: [0.1] * 100)
    with pytest.raises(ValueError, match="beyond the end"):
        transcribe_audio("solo.wav", no_separate=True, start=1e308)
    with pytest.raises(ValueError, match="one sample"):
        transcribe_audio("solo.wav", no_separate=True, duration=1e-10)
    path = tmp_path / "song.json"
    path.write_text('{"notes": []}')
    with pytest.raises(ValueError, match="only to audio"):
        load_melody(path, duration=10)


def test_crepe_pipeline_uses_native_rate_and_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    from harptab.transcribe.crepe import CrepeParams

    def load(path: object, sr: int) -> list[float]:
        assert sr == 16000
        return [0.1] * 16000

    class Tracker:
        def track(self, audio: object, sr: int) -> PitchTrack:
            assert sr == 16000
            return PitchTrack([0, 0.1, 0.2], [440] * 3, [1] * 3)

    def factory(backend: str, params: object) -> Tracker:
        assert backend == "crepe"
        assert isinstance(params, CrepeParams)
        return Tracker()

    monkeypatch.setattr("harptab.transcribe.load.load_audio", load)
    monkeypatch.setattr("harptab.pipeline.get_tracker", factory)
    messages: list[str] = []
    melody = transcribe_audio(
        "solo.wav", no_separate=True, pitch_backend="crepe", progress=messages.append
    )
    assert melody.notes[0].pitch == 69
    assert "Tracking pitch with CREPE..." in messages
