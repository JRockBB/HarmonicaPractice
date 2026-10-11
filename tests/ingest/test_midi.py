from pathlib import Path

import mido
import pytest

from harptab.ingest.midi import load_midi
from harptab.models import Melody
from scripts.fixtures_to_midi import write_midi


def test_fixture_roundtrip(melody_fixture: tuple[Path, Melody], tmp_path: Path) -> None:
    _, original = melody_fixture
    path = tmp_path / "fixture.mid"
    write_midi(original, path)
    loaded = load_midi(path)
    assert [n.pitch for n in loaded.notes] == [n.pitch for n in original.notes]
    assert [n.start for n in loaded.notes] == pytest.approx(
        [n.start for n in original.notes], abs=0.01
    )
    assert [n.duration for n in loaded.notes] == pytest.approx(
        [n.duration for n in original.notes], abs=0.01
    )
    assert loaded.key_estimate == original.key_estimate
    assert loaded.tempo_bpm == original.tempo_bpm


def test_global_tempo_map_and_named_melody(tmp_path: Path) -> None:
    midi = mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.MetaMessage("set_tempo", tempo=500000),
                mido.MetaMessage("set_tempo", tempo=1000000, time=480),
            ]
        )
    )
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.MetaMessage("track_name", name="Lead vocal"),
                mido.Message("note_on", note=60),
                mido.Message("note_off", note=60, time=960),
                mido.Message("note_on", note=62),
                mido.Message("note_on", note=62, velocity=0, time=480),
            ]
        )
    )
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.Message("note_on", note=100),
                mido.Message("note_off", note=100, time=1440),
            ]
        )
    )
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.MetaMessage("track_name", name="Melody drums"),
                mido.Message("note_on", channel=9, note=110),
                mido.Message("note_off", channel=9, note=110, time=1440),
            ]
        )
    )
    path = tmp_path / "tempo.mid"
    midi.save(path)
    tune = load_midi(path)
    assert [n.pitch for n in tune.notes] == [60, 62]
    assert [n.start for n in tune.notes] == [0, 1.5]
    assert [n.duration for n in tune.notes] == [1.5, 1.0]
    assert tune.beats == [0, 0.5, 1.5, 2.5]


def test_type_zero_channels_and_unclosed_note(tmp_path: Path) -> None:
    midi = mido.MidiFile(type=0, ticks_per_beat=480)
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.Message("note_on", channel=0, note=48),
                mido.Message("note_on", channel=1, note=72),
                mido.Message("note_off", channel=0, note=48, time=480),
                mido.MetaMessage("end_of_track", time=480),
            ]
        )
    )
    path = tmp_path / "channels.mid"
    midi.save(path)
    tune = load_midi(path)
    assert len(tune.notes) == 1
    assert tune.notes[0].pitch == 72
    assert tune.notes[0].duration == 1


def test_type_two_rejected(tmp_path: Path) -> None:
    midi = mido.MidiFile(type=2)
    midi.tracks.append(mido.MidiTrack())
    path = tmp_path / "independent.mid"
    midi.save(path)
    with pytest.raises(ValueError, match="independent timelines"):
        load_midi(path)
