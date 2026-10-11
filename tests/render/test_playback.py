import struct
import wave
from pathlib import Path

import pytest

from harptab.core.assign import assign
from harptab.core.instrument import HarmonicaModel
from harptab.models import Melody, NoteEvent
from harptab.playback import PreviewOptions, preview_wav


def test_preview_retains_pitch_slowed_timing_and_silent_gaps(tmp_path: Path) -> None:
    path = tmp_path / "practice.wav"
    melody = Melody([NoteEvent(69, 30, 0.2), NoteEvent(69, 30.4, 0.2)])
    preview_wav(path, melody, options=PreviewOptions(sample_rate=8000, speed=0.5))
    with wave.open(str(path)) as audio:
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getframerate() == 8000
        assert audio.getnframes() == 9600
        samples = struct.unpack("<9600h", audio.readframes(9600))
    assert max(samples) > 0
    assert all(value == 0 for value in samples[3200:6400])
    assert samples[0] == samples[3199] == samples[6400] == samples[-1] == 0
    # Slowing changes duration, never pitch: estimate frequency from positive zero crossings.
    crossings = sum(a <= 0 < b for a, b in zip(samples[800:2400], samples[801:2401], strict=True))
    assert crossings / 0.2 == pytest.approx(440, abs=5)


def test_arranged_preview_omits_unplayable_and_applies_transposition(tmp_path: Path) -> None:
    path = tmp_path / "arranged.wav"
    melody = Melody([NoteEvent(36, 0, 0.2), NoteEvent(57, 0.2, 0.2)])
    arrangement = assign(melody, HarmonicaModel(0), transpose=12)
    assert arrangement.actions[0] is None
    preview_wav(path, melody, arrangement, options=PreviewOptions(sample_rate=8000, speed=1))
    with wave.open(str(path)) as audio:
        samples = struct.unpack("<3200h", audio.readframes(3200))
    assert not any(samples[:1600])
    crossings = sum(a <= 0 < b for a, b in zip(samples[1700:3100], samples[1701:3101], strict=True))
    assert crossings / (1400 / 8000) == pytest.approx(440, abs=6)


def test_preview_limits_and_empty_input_do_not_create_files(tmp_path: Path) -> None:
    path = tmp_path / "invalid.wav"
    with pytest.raises(ValueError, match="requires melody notes"):
        preview_wav(path, Melody([]))
    with pytest.raises(ValueError, match="shorter excerpt"):
        preview_wav(path, Melody([NoteEvent(60, 0, 400)]))
    assert not path.exists()
