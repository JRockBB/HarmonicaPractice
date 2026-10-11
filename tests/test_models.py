import json

import pytest

from harptab.models import Action, Arrangement, KeyEstimate, Melody, NoteEvent, Technique
from harptab.validation import validate_melody


def test_melody_roundtrip() -> None:
    original = Melody(
        [NoteEvent(60, 0, 0.5, 0.8, -3)], 120, [0, 0.5], KeyEstimate(0, "major", 1), "x"
    )
    assert Melody.from_dict(json.loads(json.dumps(original.to_dict()))) == original


def test_arrangement_roundtrip_every_technique() -> None:
    original = Arrangement(
        0, 1, 0, [Action(3, t, 1, 70) for t in Technique] + [None], 42, {"bends": 2}
    )
    assert Arrangement.from_dict(json.loads(json.dumps(original.to_dict()))) == original


def test_optional_defaults() -> None:
    melody = Melody.from_dict({"notes": [{"pitch": 60, "start": 0, "duration": 1}]})
    assert melody.notes[0].confidence == 1
    assert melody.key_estimate is None


@pytest.mark.parametrize(
    "notes",
    [
        [NoteEvent(60, 0, 1), NoteEvent(62, 0.5, 1)],
        [NoteEvent(60, -1, 1)],
        [NoteEvent(60, 0, 0)],
        [NoteEvent(128, 0, 1)],
        [NoteEvent(60, 0, float("nan"))],
        [NoteEvent(60, 0, 1, 2)],
        [NoteEvent(60, 0, 1, cents_offset=float("inf"))],
    ],
)
def test_invalid_notes_rejected(notes: list[NoteEvent]) -> None:
    with pytest.raises(ValueError):
        validate_melody(Melody(notes))


@pytest.mark.parametrize(
    "metadata",
    [
        {"tempo_bpm": 0},
        {"tempo_bpm": float("nan")},
        {"beats": [1, 0]},
        {"beats": [0, 0]},
        {"key_estimate": KeyEstimate(12, "major", 1)},
        {"key_estimate": KeyEstimate(0, "dorian", 1)},
    ],
)
def test_invalid_metadata_rejected(metadata: dict) -> None:
    with pytest.raises(ValueError):
        validate_melody(Melody([], **metadata))
