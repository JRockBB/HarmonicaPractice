from itertools import pairwise, product
from pathlib import Path

import pytest

from harptab.core.assign import assign
from harptab.core.difficulty import OVER_NOTES, action_cost, node_cost, transition_cost
from harptab.core.instrument import HarmonicaModel
from harptab.models import Melody, NoteEvent, Technique
from harptab.render.text import action_token


def melody(pitches: list[int]) -> Melody:
    return Melody([NoteEvent(p, i, 1) for i, p in enumerate(pitches)])


def test_fixture_tabs(melody_fixture: tuple[Path, Melody]) -> None:
    path, tune = melody_fixture
    expected = path.with_name(path.name.replace(".melody.json", ".expected.txt")).read_text()
    header, tokens = expected.strip().split("\n", 1)
    key, position = map(int, header.removeprefix("# harp_key, position: ").split(","))
    arrangement = assign(tune, HarmonicaModel(key))
    assert arrangement.position == position
    assert " ".join(action_token(a) for a in arrangement.actions) == " ".join(tokens.split())


@pytest.mark.parametrize("pitches,hole", [([64, 67, 72], 3), ([62, 67, 71], 2)])
def test_duplicate_g_depends_on_neighbors(pitches: list[int], hole: int) -> None:
    action = assign(melody(pitches), HarmonicaModel(0)).actions[1]
    assert action is not None and action.hole == hole


def test_gap_preserves_previous_action() -> None:
    result = assign(melody([62, 48, 67, 71]), HarmonicaModel(0))
    assert result.actions[1] is None
    assert result.actions[2].hole == 2
    assert result.stats["unplayable"] == 1


@pytest.mark.parametrize("pitches", [[62, 67, 71], [64, 67, 72, 67], [67, 48, 67], [63, 78, 82]])
def test_viterbi_matches_exhaustive_paths(pitches: list[int]) -> None:
    harp = HarmonicaModel(0)
    result = assign(melody(pitches), harp)
    choices = [
        [a for a in harp.actions_for_pitch(p) if a.technique not in OVER_NOTES] for p in pitches
    ]
    missing = sum(not layer for layer in choices) * action_cost(None)
    paths = product(*(layer for layer in choices if layer))
    costs = [
        missing
        + sum(node_cost(a) for a in path)
        + sum(transition_cost(a, b) for a, b in pairwise(path))
        for path in paths
    ]
    assert result.cost == pytest.approx(min(costs))
    assert result == assign(melody(pitches), harp)


def test_overblows_are_opt_in_and_empty_is_valid() -> None:
    tune = melody([63, 97])
    assert assign(tune, HarmonicaModel(0)).actions == [None, None]
    enabled = assign(tune, HarmonicaModel(0), overblows=True)
    assert [a.technique for a in enabled.actions] == [Technique.OVERBLOW, Technique.OVERDRAW]
    assert enabled.stats["overblows"] == 2
    assert assign(Melody([]), HarmonicaModel(0)).cost == 0
