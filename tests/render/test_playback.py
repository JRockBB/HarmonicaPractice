import struct
import wave
from importlib.resources import files
from io import BytesIO
from math import cos, hypot, pi, sin
from pathlib import Path

import pytest

from harptab.core.assign import assign
from harptab.core.instrument import HarmonicaModel
from harptab.models import Melody, NoteEvent
from harptab.playback import PreviewOptions, preview_wav


@pytest.mark.parametrize("voice", ["harmonica", "sine"])
def test_preview_retains_pitch_slowed_timing_and_silent_gaps(tmp_path: Path, voice: str) -> None:
    path = tmp_path / "practice.wav"
    melody = Melody([NoteEvent(69, 30, 0.2), NoteEvent(69, 30.4, 0.2)])
    preview_wav(path, melody, options=PreviewOptions(sample_rate=8000, speed=0.5, voice=voice))
    with wave.open(str(path)) as audio:
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getframerate() == 8000
        assert audio.getnframes() == 9600
        samples = struct.unpack("<9600h", audio.readframes(9600))
    assert max(samples) > 0
    assert all(value == 0 for value in samples[3200:6400])
    assert samples[0] == samples[3199] == samples[6400] == samples[-1] == 0
    # Recorded reeds have strong overtones, so zero crossings don't measure their fundamental.
    fundamental = max(
        range(420, 461), key=lambda hz: _spectral_amplitude(samples[800:2400], hz, 8000)
    )
    assert fundamental == pytest.approx(440, abs=3)


@pytest.mark.parametrize("voice", ["harmonica", "sine"])
def test_arranged_preview_omits_unplayable_and_applies_transposition(
    tmp_path: Path, voice: str
) -> None:
    path = tmp_path / "arranged.wav"
    melody = Melody([NoteEvent(36, 0, 0.2), NoteEvent(57, 0.2, 0.2)])
    arrangement = assign(melody, HarmonicaModel(0), transpose=12)
    assert arrangement.actions[0] is None
    preview_wav(
        path, melody, arrangement, options=PreviewOptions(sample_rate=8000, speed=1, voice=voice)
    )
    with wave.open(str(path)) as audio:
        samples = struct.unpack("<3200h", audio.readframes(3200))
    assert not any(samples[:1600])
    fundamental = max(
        range(420, 461), key=lambda hz: _spectral_amplitude(samples[1800:3000], hz, 8000)
    )
    assert fundamental == pytest.approx(440, abs=4)


def test_preview_limits_and_empty_input_do_not_create_files(tmp_path: Path) -> None:
    path = tmp_path / "invalid.wav"
    with pytest.raises(ValueError, match="requires melody notes"):
        preview_wav(path, Melody([]))
    with pytest.raises(ValueError, match="shorter excerpt"):
        preview_wav(path, Melody([NoteEvent(60, 0, 400)]))
    assert not path.exists()


def _read_samples(path: Path) -> tuple[int, ...]:
    with wave.open(str(path)) as audio:
        size = audio.getnframes()
        return struct.unpack(f"<{size}h", audio.readframes(size))


def _spectral_amplitude(samples: tuple[int, ...], hz: float, rate: int) -> float:
    # A Hann window limits leakage when a note is not an integer number of cycles.
    windowed = [
        value * (1 - cos(2 * pi * i / (len(samples) - 1))) / 2 for i, value in enumerate(samples)
    ]
    real = sum(value * cos(2 * pi * hz * i / rate) for i, value in enumerate(windowed))
    imaginary = sum(value * sin(2 * pi * hz * i / rate) for i, value in enumerate(windowed))
    return hypot(real, imaginary) / len(samples)


def test_default_voice_has_reed_harmonics_and_sine_remains_pure(tmp_path: Path) -> None:
    melody = Melody([NoteEvent(69, 0, 0.6)])
    default, sine = tmp_path / "harmonica.wav", tmp_path / "sine.wav"
    preview_wav(default, melody, options=PreviewOptions(sample_rate=8000, speed=1))
    preview_wav(sine, melody, options=PreviewOptions(sample_rate=8000, speed=1, voice="sine"))
    reed_samples, sine_samples = _read_samples(default)[800:4000], _read_samples(sine)[800:4000]
    assert len(reed_samples) == len(sine_samples)
    fundamental = _spectral_amplitude(reed_samples, 440, 8000)
    second = _spectral_amplitude(reed_samples, 880, 8000)
    third = _spectral_amplitude(reed_samples, 1320, 8000)
    assert second + third > 0.2 * fundamental
    assert _spectral_amplitude(sine_samples, 880, 8000) < (
        0.001 * _spectral_amplitude(sine_samples, 440, 8000)
    )


def test_high_reed_notes_do_not_fold_harmonics_below_nyquist(tmp_path: Path) -> None:
    path = tmp_path / "high.wav"
    preview_wav(
        path, Melody([NoteEvent(84, 0, 0.7)]), options=PreviewOptions(sample_rate=8000, speed=1)
    )
    samples = _read_samples(path)[800:4800]
    hz = 440 * 2 ** ((84 - 69) / 12)
    fundamental = _spectral_amplitude(samples, hz, 8000)
    assert _spectral_amplitude(samples, 3 * hz, 8000) > 0.2 * fundamental
    # The fourth harmonic exceeds Nyquist; an unfiltered oscillator aliases here.
    assert _spectral_amplitude(samples, 8000 - 4 * hz, 8000) < 0.01 * fundamental


@pytest.mark.parametrize("voice", ["harmonica", "sine"])
def test_full_amplitude_short_notes_are_bounded_and_reproducible(
    tmp_path: Path, voice: str
) -> None:
    path = tmp_path / "loud.wav"
    again = tmp_path / "again.wav"
    melody = Melody([NoteEvent(48, 0, 0.15), NoteEvent(72, 0.2, 0.001), NoteEvent(107, 0.3, 0.15)])
    options = PreviewOptions(sample_rate=8000, speed=1, amplitude=1, voice=voice)
    preview_wav(path, melody, options=options)
    preview_wav(again, melody, options=options)
    assert path.read_bytes() == again.read_bytes()
    samples = _read_samples(path)
    assert 0 < max(abs(sample) for sample in samples) <= 32767
    assert samples[0] == samples[1199] == samples[1600] == samples[1607] == samples[-1] == 0
    assert not any(samples[1200:1600])
    assert not any(samples[1608:2400])


def test_unknown_preview_voice_is_rejected() -> None:
    with pytest.raises(ValueError, match="voice must be"):
        PreviewOptions(voice="telephone")


def test_harmonica_plays_the_recorded_waveform_and_holds_its_loop(tmp_path: Path) -> None:
    path = tmp_path / "recorded.wav"
    preview_wav(path, Melody([NoteEvent(72, 0, 3)]), options=PreviewOptions(speed=1, amplitude=1))
    played = _read_samples(path)
    asset = files("harptab").joinpath("assets").joinpath("harmonica").joinpath("72.wav")
    with wave.open(BytesIO(asset.read_bytes())) as audio:
        original = struct.unpack(f"<{audio.getnframes()}h", audio.readframes(audio.getnframes()))
    # With no pitch/rate shift, the recording's detailed waveform must survive playback.
    left, right = original[1000:10000], played[1000:10000]
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    energy = sum(a * a for a in left) * sum(b * b for b in right)
    assert dot / energy**0.5 > 0.99999
    # This note exceeds the source duration: the sustain stays audible, without a new attack.
    assert len(played) == 3 * 22050
    for begin in range(22050, 2 * 22050, 1000):
        assert max(abs(x) for x in played[begin : begin + 1000]) > 1000
    assert played[0] == played[-1] == 0
