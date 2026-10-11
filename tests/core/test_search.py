import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from harptab.core.search import search
from harptab.models import KeyEstimate, Melody, NoteEvent


def melody(pitches: list[int]) -> Melody:
    return Melody([NoteEvent(p, i, 1) for i, p in enumerate(pitches)])


@given(st.lists(st.integers(0, 127), min_size=1, max_size=16))
@settings(max_examples=40, deadline=None)
def test_play_along_always_preserves_pitch(pitches: list[int]) -> None:
    for result in search(melody(pitches)):
        assert result.transpose == 0
        assert all(a is None or a.pitch == p for a, p in zip(result.actions, pitches, strict=True))


@given(st.lists(st.integers(36, 96), min_size=1, max_size=6))
@settings(max_examples=12, deadline=None)
def test_practice_actions_match_reported_total_shift(pitches: list[int]) -> None:
    for result in search(melody(pitches), mode="practice", harps=[0]):
        assert all(
            a is None or a.pitch == p + result.transpose
            for a, p in zip(result.actions, pitches, strict=True)
        )


def test_octave_moves_are_reported_and_owned_harps_respected() -> None:
    tune = melody([48, 50, 52, 53, 55, 57, 59, 60])
    assert search(tune, harps=[0])[0].stats["unplayable"] > 0
    practice = search(tune, mode="practice", harps=[0])[0]
    assert practice.transpose >= 12
    assert practice.stats["unplayable"] == 0
    assert practice.harp_key == 0
    assert search(tune, harps=[7, 9, 7], top_n=20) == search(tune, harps=[9, 7], top_n=20)


def test_position_uses_transposed_tonic() -> None:
    tune = melody([60, 62, 64])
    tune.key_estimate = KeyEstimate(0, "major", 1)
    from harptab.core.positions import position_of

    for result in search(tune, mode="practice", harps=[9], top_n=10):
        assert result.position == position_of(9, result.transpose % 12)


def test_empty_and_invalid_search() -> None:
    assert search(Melody([])) == []
    for kwargs in ({"harps": []}, {"top_n": 0}, {"mode": "bad"}, {"skill": "bad"}):
        with pytest.raises(ValueError):
            search(melody([60]), **kwargs)


def test_full_c_major_middle_octave_prefers_c_harp_first_position() -> None:
    tune = melody([72, 74, 76, 77, 79, 81, 83, 84])
    tune.key_estimate = KeyEstimate(0, "major", 1)
    best = search(tune)[0]
    assert (best.harp_key, best.position) == (0, 1)
    assert best.stats["bends"] == best.stats["unplayable"] == 0
