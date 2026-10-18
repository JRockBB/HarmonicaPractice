import json
import math
import wave
from array import array

import mido
import pytest

from harptab.cli import main
from harptab.core.chords import assign_chords
from harptab.core.instrument import HarmonicaModel
from harptab.ingest.chords import chord_events
from harptab.ingest.midi import load_midi, load_midi_score
from harptab.models import ChordEvent, ChordScore, NoteEvent
from harptab.pipeline import load_score
from harptab.playback import PreviewOptions, preview_chords_wav
from harptab.render.chords import render_chord_practice
from harptab.render.practice import PracticeOptions


def test_json_cli_chords_roundtrip_tabs_and_audio(tmp_path, capsys):
    score = ChordScore([ChordEvent((60, 64, 67), 2, 0.3), ChordEvent((62, 67, 71), 2.5, 0.3)])
    source = tmp_path / "chords.json"
    source.write_text(json.dumps(score.to_dict()))
    output = tmp_path / "result.json"
    preview = tmp_path / "chords.wav"
    assert (
        main(
            [
                str(source),
                "--chords",
                "--harps",
                "C",
                "--format",
                "json",
                "-o",
                str(output),
                "--preview",
                str(preview),
                "--practice-speed",
                "0.5",
            ]
        )
        == 0
    )
    assert load_score(output) == score
    with wave.open(str(preview)) as audio:
        assert audio.getnframes() == round(0.8 * 22050 / 0.5)
    guide = tmp_path / "guide.md"
    assert (
        main([str(output), "--chords", "--harps", "C", "--format", "practice", "-o", str(guide)])
        == 0
    )
    assert "`[1 2 3]`" in guide.read_text(encoding="utf-8")
    assert "holes 1, 2, 3 together" in guide.read_text(encoding="utf-8")
    assert not capsys.readouterr().out


def test_chord_reductions_and_rests_are_explicit():
    score = ChordScore([ChordEvent((71, 74, 78), 1, 0.4), ChordEvent((71, 74, 79), 2, 0.4)])
    arrangement = assign_chords(score, HarmonicaModel(7))
    text = render_chord_practice(score, arrangement, options=PracticeOptions(speed=0.5))
    assert "Omitted: B4, D5" in text
    assert "[5 6 7]" in text
    assert "1.20s" in text


@pytest.mark.parametrize("voice", ["sine", "harmonica"])
def test_playback_contains_all_chord_pitches_and_silent_gaps(tmp_path, voice):
    pitches = (72, 76, 79)
    score = ChordScore([ChordEvent(pitches, 1, 0.4), ChordEvent(pitches, 1.6, 0.4)])
    arrangement = assign_chords(score, HarmonicaModel(0))
    path = tmp_path / "poly.wav"
    preview_chords_wav(
        path, score, arrangement, options=PreviewOptions(sample_rate=8000, speed=0.5, voice=voice)
    )
    with wave.open(str(path)) as audio:
        samples = array("h", audio.readframes(audio.getnframes()))
        assert audio.getnframes() == 16000
    assert max(map(abs, samples)) <= 8192
    assert not any(samples[6400:9600])
    window = samples[1000:5000]

    def strength(hz):
        real = sum(x * math.cos(2 * math.pi * hz * i / 8000) for i, x in enumerate(window))
        imag = sum(x * math.sin(2 * math.pi * hz * i / 8000) for i, x in enumerate(window))
        return math.hypot(real, imag)

    for pitch in pitches:
        hz = 440 * 2 ** ((pitch - 69) / 12)
        assert strength(hz) > 5 * strength(hz * 2 ** (0.5 / 12))


def test_symbolic_chords_keep_independent_endings_repeats_and_rests():
    events = chord_events(
        [
            NoteEvent(60, 0, 1),
            NoteEvent(64, 0, 0.5),
            NoteEvent(67, 0, 0.5),
            NoteEvent(64, 0.5, 0.5),
            NoteEvent(67, 0.5, 0.5),
            NoteEvent(72, 1.5, 0.5),
        ]
    )
    assert [(e.pitches, e.start, e.duration) for e in events] == [
        ((60, 64, 67), 0, 0.5),
        ((60, 64, 67), 0.5, 0.5),
        ((72,), 1.5, 0.5),
    ]


def test_midi_mode_preserves_harmony_across_tracks_and_skips_drums(tmp_path):
    path = tmp_path / "poly.mid"
    midi = mido.MidiFile(ticks_per_beat=480)
    for channel, pitch in ((0, 60), (1, 64), (2, 67), (9, 80)):
        midi.tracks.append(
            mido.MidiTrack(
                [
                    mido.Message("note_on", note=pitch, velocity=80, channel=channel, time=0),
                    mido.Message("note_off", note=pitch, channel=channel, time=480),
                ]
            )
        )
    midi.save(path)
    assert load_midi_score(path).events[0].pitches == (60, 64, 67)
    assert load_midi(path).notes[0].pitch == 67


def test_chord_input_is_not_silently_reduced_in_default_mode(tmp_path, capsys):
    path = tmp_path / "score.json"
    path.write_text(json.dumps(ChordScore([ChordEvent((60, 64, 67), 0, 0.2)]).to_dict()))
    assert main([str(path)]) == 2
    assert "--chords" in capsys.readouterr().err


def test_chord_output_cannot_overwrite_source(tmp_path):
    path = tmp_path / "score.json"
    data = json.dumps(ChordScore([ChordEvent((60, 64, 67), 0, 0.2)]).to_dict())
    path.write_text(data)
    assert main([str(path), "--chords", "--preview", str(path)]) == 2
    assert path.read_text() == data


def test_harmony_source_cannot_be_overwritten_even_before_loading(tmp_path):
    melody = tmp_path / "melody.json"
    audio = tmp_path / "stem.wav"
    audio.write_bytes(b"keep")
    assert main([str(melody), "--harmony-audio", str(audio), "-o", str(audio)]) == 2
    assert audio.read_bytes() == b"keep"
