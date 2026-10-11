from pathlib import Path

import pytest

from harptab.pipeline import transcribe_audio
from harptab.transcribe.pitch import PitchTrack


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
    messages: list[str] = []
    melody = transcribe_audio(Path("solo.wav"), no_separate=True, progress=messages.append)
    assert len(melody.notes) == 1
    assert melody.notes[0].pitch == 69
    assert melody.notes[0].duration == pytest.approx(2535 / 22050)
    assert melody.source == "solo.wav"
    assert messages == ["Loading audio...", "Tracking pitch with pYIN...", "Segmenting notes..."]
