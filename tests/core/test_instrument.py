import pytest

from harptab.core.instrument import HarmonicaModel, Tuning
from harptab.models import Technique

BLOW = [60, 64, 67, 72, 76, 79, 84, 88, 91, 96]
DRAW = [62, 67, 71, 74, 77, 81, 83, 86, 89, 93]


def all_actions(harp: HarmonicaModel) -> set[tuple[int, Technique, int, int]]:
    low, high = harp.range()
    return {
        (a.hole, a.technique, a.bend_semitones, a.pitch)
        for pitch in range(low, high + 1)
        for a in harp.actions_for_pitch(pitch)
    }


def test_exact_reference_actions() -> None:
    expected = {(i, Technique.BLOW, 0, pitch) for i, pitch in enumerate(BLOW, 1)}
    expected |= {(i, Technique.DRAW, 0, pitch) for i, pitch in enumerate(DRAW, 1)}
    for hole, depths in {1: 1, 2: 2, 3: 3, 4: 1, 6: 1}.items():
        expected |= {
            (hole, Technique.DRAW_BEND, d, DRAW[hole - 1] - d) for d in range(1, depths + 1)
        }
    for hole, depths in {8: 1, 9: 1, 10: 2}.items():
        expected |= {
            (hole, Technique.BLOW_BEND, d, BLOW[hole - 1] - d) for d in range(1, depths + 1)
        }
    expected |= {(h, Technique.OVERBLOW, 0, p) for h, p in [(1, 63), (4, 75), (5, 78), (6, 82)]}
    expected |= {(h, Technique.OVERDRAW, 0, p) for h, p in [(7, 85), (9, 92), (10, 97)]}
    assert all_actions(HarmonicaModel(0)) == expected


@pytest.mark.parametrize("key", range(12))
def test_every_key_is_shifted_reference(key: int) -> None:
    shift = key if key <= 6 else key - 12
    expected = {(h, t, d, p + shift) for h, t, d, p in all_actions(HarmonicaModel(0))}
    assert all_actions(HarmonicaModel(key)) == expected


def test_low_harp_and_custom_tuning() -> None:
    assert HarmonicaModel(5, octave_shift=-1).range() == (53, 90)
    custom = Tuning(tuple(BLOW), (61, *DRAW[1:]))
    assert not any(
        a.hole == 1 and a.technique == Technique.DRAW_BEND
        for a in HarmonicaModel(0, custom).actions_for_pitch(61)
    )
    assert HarmonicaModel(0).actions_for_pitch(59) == []


@pytest.mark.parametrize("key", [-1, 12, True, 1.5])
def test_invalid_key(key: int) -> None:
    with pytest.raises(ValueError):
        HarmonicaModel(key)
