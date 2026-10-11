import json

import pytest

from harptab.core.assign import assign
from harptab.core.instrument import HarmonicaModel
from harptab.models import Action, Arrangement, KeyEstimate, Melody, NoteEvent, Technique
from harptab.render.json import render_json
from harptab.render.text import TextOptions, render_text


def test_all_tokens_snapshot() -> None:
    actions = [
        Action(4, Technique.BLOW),
        Action(4, Technique.DRAW),
        Action(3, Technique.DRAW_BEND, 1),
        Action(3, Technique.DRAW_BEND, 2),
        Action(3, Technique.DRAW_BEND, 3),
        Action(8, Technique.BLOW_BEND, 1),
        Action(4, Technique.OVERBLOW),
        Action(7, Technique.OVERDRAW),
        None,
    ]
    tune = Melody([NoteEvent(72, i, 1) for i in range(9)], key_estimate=KeyEstimate(0, "major", 1))
    result = Arrangement(
        0, 1, 0, actions, 68.0, {"bends": 4, "overblows": 2, "unplayable": 1, "jumps": 1}
    )
    assert render_text(tune, result) == (
        "Song key: C major (provided)\nHarp: C, 1st position\nTranspose: +0 semitones\n"
        "Difficulty: 4 bends, 2 over-notes, 1 unplayable, 1 jumps; cost 68.00\n\n"
        "4 -4 -3' -3'' -3''' 8' 4o 7o ?\n"
    )
    data = json.loads(render_json(tune, result, alternatives=[result]))
    assert Arrangement.from_dict(data["arrangement"]) == result
    assert Melody.from_dict(data["melody"]) == tune
    assert len(data["alternatives"]) == 1


def test_phrase_rests_tempo_and_line_length() -> None:
    tune = Melody([NoteEvent(72, t, 0.2) for t in [0, 0.2, 1.2, 2.6]], tempo_bpm=60)
    result = assign(tune, HarmonicaModel(0))
    # At 60 BPM, 0.8 seconds silence stays on the line; 1.2 seconds starts a phrase.
    assert render_text(tune, result).endswith("4 4 4\n4\n")
    assert render_text(tune, result, options=TextOptions(max_tokens=2)).endswith("4 4\n4\n4\n")


def test_mismatched_lengths_rejected() -> None:
    tune = Melody([NoteEvent(72, 0, 1)])
    arrangement = Arrangement(0, 1, 0, [], 0, {})
    for renderer in (render_text, render_json):
        with pytest.raises(ValueError, match="one action"):
            renderer(tune, arrangement)
