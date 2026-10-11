from pathlib import Path

import pytest

from harptab.models import Melody
from harptab.transcribe.pitch import PyinParams, PyinTracker, get_tracker
from harptab.transcribe.segment import segment

np = pytest.importorskip("numpy")
pytest.importorskip("librosa")
pytest.importorskip("mir_eval")
pytestmark = pytest.mark.audio


def test_sine_melody_voiced_frame_accuracy() -> None:
    sr = 22050
    pitches = [60, 64, 67, 72]
    samples = np.concatenate(
        [
            0.4 * np.sin(2 * np.pi * 440 * 2 ** ((p - 69) / 12) * np.arange(sr // 2) / sr)
            for p in pitches
        ]
    )
    track = PyinTracker().track(samples, sr)
    actual = np.array(track.f0_hz)
    times = np.array(track.times)
    expected = np.array([440 * 2 ** ((pitches[min(int(t / 0.5), 3)] - 69) / 12) for t in times])
    voiced = np.isfinite(actual)
    assert voiced.mean() >= 0.95
    cents = 1200 * np.log2(actual[voiced] / expected[voiced])
    assert np.mean(np.abs(cents) <= 50) >= 0.95


@pytest.mark.parametrize("variant", ["clean", "vibrato"])
def test_fixture_note_f_measure(melody_fixture: tuple[Path, Melody], variant: str) -> None:
    from eval.metrics import score
    from eval.synth import synthesize

    _, melody = melody_fixture
    signal, reference = synthesize(melody, variant)
    track = PyinTracker().track(signal, 22050)
    estimated = Melody(segment(track))
    result = score(reference, estimated, track)
    assert result.onset_f1 >= 0.9, (result, [(n.pitch, n.start) for n in estimated.notes])


def test_noise_signal_and_silence() -> None:
    from eval.metrics import score
    from eval.synth import synthesize
    from harptab.models import NoteEvent

    melody = Melody([NoteEvent(69, 0.1, 1)])
    signal, reference = synthesize(melody, "noise")
    track = PyinTracker().track(signal, 22050)
    assert score(reference, Melody(segment(track)), track).onset_f1 == 1
    assert not segment(PyinTracker().track(np.zeros(22050), 22050))
    assert PyinTracker().track([], 22050).times == []


def test_invalid_input_and_backend() -> None:
    for samples in (np.zeros((2, 100)), np.array([np.nan])):
        with pytest.raises(ValueError, match="mono signal"):
            PyinTracker().track(samples, 22050)
    with pytest.raises(ValueError, match="frequency bounds"):
        PyinTracker(PyinParams(fmax=12000)).track([0.0], 22050)
    with pytest.raises(ValueError, match="not implemented"):
        get_tracker("unknown")
