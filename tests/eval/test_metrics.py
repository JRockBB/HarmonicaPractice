import pytest

pytest.importorskip("mir_eval")
pytestmark = pytest.mark.audio


def test_metrics_require_pitch_and_time_and_penalize_missing_notes() -> None:
    from eval.metrics import score, token_accuracy
    from harptab.models import Melody, NoteEvent
    from harptab.transcribe.pitch import PitchTrack

    reference = Melody([NoteEvent(69, 0.1, 0.5)])
    track = PitchTrack([0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6], [0, 440, 440, 440, 440, 440, 0], [1] * 7)
    exact = score(reference, reference, track)
    assert exact.onset_f1 == exact.offset_f1 == exact.raw_pitch_accuracy == 1
    wrong_pitch = score(reference, Melody([NoteEvent(70, 0.1, 0.5)]), track)
    late = score(reference, Melody([NoteEvent(69, 0.3, 0.5)]), track)
    assert wrong_pitch.onset_f1 == late.onset_f1 == 0
    assert token_accuracy(["4", "-4", "5"], ["4", "5"]) == pytest.approx(2 / 3)
    assert token_accuracy(["4"], ["-4"]) == 0
    assert token_accuracy([], []) == 1
