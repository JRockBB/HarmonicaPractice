import pytest

from harptab.core.positions import estimate_key, harp_for, position_of
from harptab.models import KeyEstimate, Melody, NoteEvent


@pytest.mark.parametrize("song", range(12))
@pytest.mark.parametrize("position", range(1, 13))
def test_all_positions_roundtrip(song: int, position: int) -> None:
    assert position_of(harp_for(song, position), song) == position


def test_examples_and_estimation() -> None:
    assert harp_for(4, 2) == 9
    assert [position_of(0, key) for key in (0, 7, 2, 9, 4, 5)] == [1, 2, 3, 4, 5, 12]
    major = Melody([NoteEvent(p, i, 1) for i, p in enumerate([60, 62, 64, 65, 67, 69, 71, 72])])
    assert estimate_key(major).tonic == 0
    assert estimate_key(major).mode == "major"
    major.key_estimate = KeyEstimate(9, "minor", 0.8)
    assert estimate_key(major) == major.key_estimate


@pytest.mark.parametrize("position", [0, 13, True])
def test_invalid_position(position: int) -> None:
    with pytest.raises(ValueError):
        harp_for(0, position)
