import pytest

from harptab.models import Melody, NoteEvent
from harptab.transcribe.harmony import HarmonyParams, harmonize

pytestmark = pytest.mark.audio


def test_persistent_harmony_keeps_lead_timing_and_excludes_release_tails():
    np = pytest.importorskip("numpy")
    sr = 16000
    times = np.arange(sr * 2) / sr
    audio = np.zeros(len(times))
    for pitch in (72, 76, 79):
        audio += 0.2 * np.sin(2 * np.pi * 440 * 2 ** ((pitch - 69) / 12) * times)
    # A fleeting neighboring tone should not become persistent harmony.
    audio[: round(0.025 * sr)] += 0.5 * np.sin(2 * np.pi * 622.25 * times[: round(0.025 * sr)])
    melody = Melody([NoteEvent(79, 0.1, 0.5), NoteEvent(79, 1, 0.5)])
    score = harmonize(melody, audio, sr)
    assert [e.pitches for e in score.events] == [(72, 76, 79), (72, 76, 79)]
    assert [(e.start, e.duration, e.lead) for e in score.events] == [(0.1, 0.5, 79), (1, 0.5, 79)]


def test_solo_harmonics_do_not_invent_lower_chords():
    np = pytest.importorskip("numpy")
    sr = 16000
    times = np.arange(sr) / sr
    hz = 440 * 2 ** ((79 - 69) / 12)
    audio = sum(0.2 / h * np.sin(2 * np.pi * hz * h * times) for h in range(1, 5))
    score = harmonize(Melody([NoteEvent(79, 0.1, 0.7)]), audio, sr)
    assert score.events[0].pitches == (79,)


def test_silence_and_bad_source_timestamps():
    score = harmonize(Melody([NoteEvent(79, 0.1, 0.5)]), [0.0] * 16000, 16000)
    assert score.events[0].pitches == (79,)
    with pytest.raises(ValueError, match="timestamps"):
        harmonize(Melody([NoteEvent(79, 2, 0.5)]), [0.0] * 16000, 16000)
    with pytest.raises(ValueError):
        HarmonyParams(max_voices=0)


def test_reviewed_audio_chord_cli_keeps_source_time_and_exports_all_voices(tmp_path, capsys):
    import json

    from harptab.cli import main

    np = pytest.importorskip("numpy")
    sf = pytest.importorskip("soundfile")
    sr = 22050
    t = np.arange(sr) / sr
    source = tmp_path / "stem.wav"
    sf.write(
        source,
        sum(0.1 * np.sin(2 * np.pi * 440 * 2 ** ((p - 69) / 12) * t) for p in (72, 76, 79)),
        sr,
    )
    melody = tmp_path / "melody.json"
    melody.write_text(json.dumps(Melody([NoteEvent(79, 0.2, 0.5)]).to_dict()))
    output = tmp_path / "chord.json"
    preview = tmp_path / "chord.wav"
    assert (
        main(
            [
                str(melody),
                "--harmony-audio",
                str(source),
                "--harps",
                "C",
                "--format",
                "json",
                "-o",
                str(output),
                "--preview",
                str(preview),
            ]
        )
        == 0
    )
    data = json.loads(output.read_text())
    assert data["score"]["events"][0]["pitches"] == [72, 76, 79]
    assert data["score"]["events"][0]["start"] == 0.2
    assert len(data["arrangement"]["voicings"][0]["actions"]) == 3
    assert not capsys.readouterr().out
