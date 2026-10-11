"""Richter harmonicas, derived from one reference reed table."""

from dataclasses import dataclass
from types import MappingProxyType

from harptab.models import Action, Technique
from harptab.validation import validate_key


@dataclass(frozen=True)
class Tuning:
    """Reference C reeds and the supported over-note holes for a tuning."""

    blow: tuple[int, ...]
    draw: tuple[int, ...]
    overblow_holes: tuple[int, ...] = (1, 4, 5, 6)
    overdraw_holes: tuple[int, ...] = (7, 9, 10)


TUNINGS = MappingProxyType(
    {
        "richter": Tuning(
            (60, 64, 67, 72, 76, 79, 84, 88, 91, 96),
            (62, 67, 71, 74, 77, 81, 83, 86, 89, 93),
        ),
    }
)


class HarmonicaModel:
    """Ten-hole harp. ``octave_shift`` is in whole octaves (Low F uses -1)."""

    def __init__(self, key: int, tuning: str | Tuning = "richter", octave_shift: int = 0):
        validate_key(key)
        if type(octave_shift) is not int:
            raise ValueError("octave_shift must be an integer number of octaves")
        if isinstance(tuning, str):
            if tuning not in TUNINGS:
                raise ValueError(f"unknown tuning: {tuning}")
            reeds = TUNINGS[tuning]
        else:
            reeds = tuning
        if len(reeds.blow) != 10 or len(reeds.draw) != 10:
            raise ValueError("a tuning must contain ten blow and ten draw pitches")
        self.key = key
        self.tuning = tuning
        self.octave_shift = octave_shift
        shift = (key if key <= 6 else key - 12) + 12 * octave_shift
        actions: list[Action] = []
        for hole, (blow, draw) in enumerate(zip(reeds.blow, reeds.draw, strict=True), 1):
            blow += shift
            draw += shift
            actions.extend(
                (Action(hole, Technique.BLOW, pitch=blow), Action(hole, Technique.DRAW, pitch=draw))
            )
            technique = Technique.DRAW_BEND if draw > blow else Technique.BLOW_BEND
            for depth in range(1, abs(draw - blow)):
                actions.append(Action(hole, technique, depth, max(blow, draw) - depth))
            if hole in reeds.overblow_holes and draw > blow:
                actions.append(Action(hole, Technique.OVERBLOW, pitch=draw + 1))
            if hole in reeds.overdraw_holes and blow > draw:
                actions.append(Action(hole, Technique.OVERDRAW, pitch=blow + 1))
        if any(type(a.pitch) is not int or not 0 <= a.pitch <= 127 for a in actions):
            raise ValueError("tuning and octave shift must produce MIDI pitches in 0..127")
        self._actions = tuple(actions)

    def actions_for_pitch(self, pitch: int) -> list[Action]:
        """Return all physical actions producing a MIDI pitch, including over-notes."""
        return [action for action in self._actions if action.pitch == pitch]

    def range(self) -> tuple[int, int]:
        """Return inclusive minimum and maximum MIDI pitches, including over-notes."""
        return min(a.pitch for a in self._actions), max(a.pitch for a in self._actions)
