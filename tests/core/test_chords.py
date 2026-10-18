import json
from dataclasses import replace

import pytest

from harptab.core.chords import assign_chords, search_chords, voicings_for_event
from harptab.core.instrument import HarmonicaModel
from harptab.models import Action, ChordArrangement, ChordEvent, ChordScore, Technique, Voicing
from harptab.render.chords import voicing_token
from harptab.validation import validate_chord_arrangement, validate_score, validate_voicing


@pytest.mark.parametrize(
    "key,pitches,token",
    [
        (0, (60, 64, 67), "[1 2 3]"),
        (0, (62, 67, 71), "[-1 -2 -3]"),
        (9, (71, 74, 78), "[-4 -5 -6]"),
        (7, (71, 74, 79), "[5 6 7]"),
    ],
)
def test_chords_are_simultaneous_same_breath_reeds(key, pitches, token):
    score = ChordScore([ChordEvent(pitches, 0, 0.4)])
    arrangement = assign_chords(score, HarmonicaModel(key))
    assert voicing_token(arrangement.voicings[0]) == token
    assert arrangement.stats["omitted_tones"] == 0
    validate_chord_arrangement(score, arrangement)
    assert ChordScore.from_dict(json.loads(json.dumps(score.to_dict()))) == score
    assert ChordArrangement.from_dict(json.loads(json.dumps(arrangement.to_dict()))) == arrangement


def test_mixed_breath_chord_is_reduced_without_losing_lead_or_adding_notes():
    event = ChordEvent((71, 74, 78), 0, 0.4)
    arrangement = assign_chords(ChordScore([event]), HarmonicaModel(7))
    assert voicing_token(arrangement.voicings[0]) == "-7"
    assert arrangement.stats["omitted_tones"] == 2
    assert arrangement.stats["unplayable"] == 0


def test_ranking_keeps_melody_before_buying_more_chords():
    score = ChordScore([ChordEvent((71, 74, 78), 0, 0.5), ChordEvent((71, 74, 79), 0.5, 0.5)])
    result = search_chords(score, harps=[9, 7], top_n=2)
    assert [a.harp_key for a in result] == [7, 9]
    assert all(a.transpose == 0 for a in result)
    assert result[0].stats["chords"] == 1
    assert result[1].stats["unplayable"] == 1


@pytest.mark.parametrize("key", range(12))
@pytest.mark.parametrize("direction", [Technique.BLOW, Technique.DRAW])
def test_all_keys_preserve_real_contiguous_chords(key, direction):
    harp = HarmonicaModel(key)
    for first in range(1, 9):
        actions = [
            a
            for pitch in range(128)
            for a in harp.actions_for_pitch(pitch)
            if first <= a.hole < first + 3 and a.technique == direction
        ]
        pitches = tuple(sorted(a.pitch for a in actions))
        event = ChordEvent(pitches, 0, 0.3)
        candidates = voicings_for_event(event, harp)
        assert any({a.pitch for a in v.actions} == set(pitches) for v in candidates)
        for candidate in candidates:
            validate_voicing(candidate, key)
            assert event.lead in {a.pitch for a in candidate.actions}
            assert {a.pitch for a in candidate.actions} <= set(pitches)


@pytest.mark.parametrize(
    "pitches,lead",
    [((72, 72), None), ((76, 72), None), ((), None), ((True, 72), None), ((72,), 74)],
)
def test_invalid_chord_targets_are_rejected(pitches, lead):
    with pytest.raises(ValueError):
        validate_score(ChordScore([ChordEvent(pitches, 0, 0.5, melody_pitch=lead)]))


def test_invalid_time_and_overlap_are_rejected():
    for start in (-1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            validate_score(ChordScore([ChordEvent((72,), start, 0.5)]))
    with pytest.raises(ValueError, match="non-overlapping"):
        validate_score(ChordScore([ChordEvent((72,), 0, 1), ChordEvent((74,), 0.5, 1)]))


@pytest.mark.parametrize(
    "actions",
    [
        (Action(1, Technique.BLOW, pitch=60), Action(2, Technique.DRAW, pitch=67)),
        (Action(1, Technique.BLOW, pitch=60), Action(3, Technique.BLOW, pitch=67)),
        (Action(1, Technique.DRAW_BEND, 1, 61), Action(2, Technique.DRAW, pitch=67)),
        (Action(1, Technique.BLOW, pitch=61),),
        (Action(1, Technique.BLOW, pitch=60), Action(1, Technique.BLOW, pitch=60)),
    ],
)
def test_unplayable_or_false_voicings_are_rejected(actions):
    with pytest.raises(ValueError):
        validate_voicing(Voicing(actions), 0)


def test_explicit_lead_and_transposition_are_preserved():
    score = ChordScore([ChordEvent((60, 64, 67), 0, 0.5, melody_pitch=64)])
    arrangement = assign_chords(score, HarmonicaModel(2), transpose=2)
    validate_chord_arrangement(score, arrangement)
    assert {a.pitch for a in arrangement.voicings[0].actions} == {62, 66, 69}
    bad = replace(arrangement, voicings=[Voicing((Action(3, Technique.BLOW, pitch=69),))])
    with pytest.raises(ValueError, match="retain the melody"):
        validate_chord_arrangement(score, bad)


def test_search_empty_and_invalid_requests():
    assert search_chords(ChordScore([])) == []
    with pytest.raises(ValueError):
        search_chords(ChordScore([]), harps=[])
    with pytest.raises(ValueError):
        search_chords(ChordScore([]), mode="anything")
    with pytest.raises(ValueError):
        search_chords(ChordScore([]), top_n=0)


def test_overblow_requires_opt_in_and_remains_a_single_note():
    score = ChordScore([ChordEvent((71, 74, 79), 0, 0.4)])
    harp = HarmonicaModel(9)
    assert assign_chords(score, harp).voicings == [None]
    advanced = assign_chords(score, harp, overblows=True)
    assert voicing_token(advanced.voicings[0]) == "6o"
    assert advanced.stats["omitted_tones"] == 2
    validate_chord_arrangement(score, advanced)


def test_score_metadata_roundtrips():
    from harptab.models import KeyEstimate

    score = ChordScore(
        [ChordEvent((60, 64, 67), 0, 0.5, 0.8, 64)],
        120,
        [0, 0.5],
        KeyEstimate(0, "major", 0.9),
        "synthetic",
    )
    assert ChordScore.from_dict(json.loads(json.dumps(score.to_dict()))) == score
    with pytest.raises(ValueError):
        validate_score(replace(score, tempo_bpm=float("nan")))
