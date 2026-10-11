import pytest

from harptab.core.difficulty import action_cost, transition_cost
from harptab.models import Action, Technique


@pytest.mark.parametrize(
    "technique,depth,expected",
    [
        (Technique.BLOW, 0, 0),
        (Technique.DRAW, 0, 0),
        (Technique.DRAW_BEND, 1, 1),
        (Technique.DRAW_BEND, 2, 2),
        (Technique.DRAW_BEND, 3, 3),
        (Technique.BLOW_BEND, 1, 2),
        (Technique.BLOW_BEND, 2, 2),
        (Technique.OVERBLOW, 0, 6),
        (Technique.OVERDRAW, 0, 6),
    ],
)
def test_reference_costs(technique: Technique, depth: int, expected: float) -> None:
    assert action_cost(Action(3, technique, depth)) == expected
    assert action_cost(None) == 50


def test_skill_and_movement_costs() -> None:
    bend = Action(3, Technique.DRAW_BEND, 1)
    assert action_cost(bend, "beginner") > action_cost(bend) > action_cost(bend, "advanced")
    assert transition_cost(Action(1, Technique.BLOW), Action(2, Technique.BLOW)) == 0
    assert transition_cost(Action(1, Technique.BLOW), Action(4, Technique.DRAW)) == pytest.approx(
        0.8
    )
    assert transition_cost(Action(3, Technique.DRAW), bend) == pytest.approx(0.1)
    assert transition_cost(
        Action(6, Technique.OVERBLOW), Action(7, Technique.OVERDRAW)
    ) == pytest.approx(0.2)
