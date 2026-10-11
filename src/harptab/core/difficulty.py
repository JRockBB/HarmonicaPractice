"""Shared technique and motion costs for search and assignment."""

from dataclasses import dataclass
from types import MappingProxyType

from harptab.models import Action, Technique

OVER_NOTES = frozenset((Technique.OVERBLOW, Technique.OVERDRAW))
BENDS = frozenset((Technique.DRAW_BEND, Technique.BLOW_BEND))
DRAWING = frozenset((Technique.DRAW, Technique.DRAW_BEND, Technique.OVERDRAW))


@dataclass(frozen=True)
class Difficulty:
    draw_bend: float = 1.0  # Cost per semitone of draw bend.
    blow_bend: float = 2.0  # Cost for any blow bend.
    over_note: float = 6.0  # Cost for overblows and overdraws.
    unplayable: float = 50.0  # Cost for a missing pitch.
    breath_change: float = 0.2  # Cost when airflow direction changes.
    hole_jump: float = 0.3  # Cost per hole beyond an adjacent move.
    bend_change: float = 0.1  # Cost for entering or leaving a bend.
    middle: float = 0.01  # Weak node preference for the middle register.
    center_hole: float = 5.5  # Center of the ten-hole instrument.


SKILLS = MappingProxyType(
    {
        "beginner": Difficulty(draw_bend=4.0, blow_bend=6.0, over_note=12.0),
        "intermediate": Difficulty(),
        "advanced": Difficulty(draw_bend=0.5, blow_bend=1.0, over_note=3.0),
    }
)


def costs_for(skill: str | Difficulty) -> Difficulty:
    """Resolve a named skill or explicitly supplied cost configuration."""
    if isinstance(skill, Difficulty):
        return skill
    if skill not in SKILLS:
        raise ValueError(f"unknown skill: {skill}")
    return SKILLS[skill]


def action_cost(action: Action | None, skill: str | Difficulty = "intermediate") -> float:
    """Return technique cost, with a separate penalty for an unplayable note."""
    costs = costs_for(skill)
    if action is None:
        return costs.unplayable
    if action.technique in OVER_NOTES:
        return costs.over_note
    if action.technique == Technique.DRAW_BEND:
        return costs.draw_bend * action.bend_semitones
    if action.technique == Technique.BLOW_BEND:
        return costs.blow_bend
    return 0.0


def node_cost(action: Action, skill: str | Difficulty = "intermediate") -> float:
    """Add a small middle-register preference to technique cost."""
    costs = costs_for(skill)
    return action_cost(action, costs) + costs.middle * abs(action.hole - costs.center_hole)


def transition_cost(prev: Action, next: Action, skill: str | Difficulty = "intermediate") -> float:
    """Cost the hole distance, airflow reversal and bend change between two actions."""
    costs = costs_for(skill)
    result = costs.hole_jump * max(0, abs(next.hole - prev.hole) - 1)
    result += costs.breath_change * ((prev.technique in DRAWING) != (next.technique in DRAWING))
    result += costs.bend_change * ((prev.technique in BENDS) != (next.technique in BENDS))
    return result
