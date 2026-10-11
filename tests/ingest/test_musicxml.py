import builtins
from pathlib import Path

import pytest

from harptab.ingest.musicxml import load_musicxml


def test_missing_extra_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    original = builtins.__import__

    def without_music21(name: str, *args: object, **kwargs: object) -> object:
        if name == "music21":
            raise ImportError("simulated missing optional dependency")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_music21)
    with pytest.raises(ImportError, match=r"harptab\[musicxml\]"):
        load_musicxml("unused.musicxml")


def test_musicxml_pitch_chords_and_tempo(tmp_path: Path) -> None:
    music21 = pytest.importorskip("music21")
    score = music21.stream.Score()
    part = music21.stream.Part()
    part.partName = "Melody"
    part.append(music21.tempo.MetronomeMark(number=120))
    part.append(music21.note.Note("C5", quarterLength=1))
    part.append(music21.chord.Chord(["E4", "E5"], quarterLength=1))
    part.append(music21.tempo.MetronomeMark(number=60))
    part.append(music21.note.Note("G5", quarterLength=1))
    score.append(part)
    path = tmp_path / "melody.musicxml"
    score.write("musicxml", fp=path)
    tune = load_musicxml(path)
    assert [n.pitch for n in tune.notes] == [72, 76, 79]
    assert [n.start for n in tune.notes] == pytest.approx([0, 0.5, 1])
    assert [n.duration for n in tune.notes] == pytest.approx([0.5, 0.5, 1])
