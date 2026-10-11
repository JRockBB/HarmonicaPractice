"""Standard harmonica tab notation and phrase layout."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite

from harptab.core.positions import estimate_key
from harptab.models import Action, Arrangement, Melody, Technique
from harptab.validation import validate_melody

KEY_NAMES = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")


@dataclass(frozen=True)
class TextOptions:
    phrase_rest: float = 0.6  # Minimum silence in seconds before a new phrase.
    max_tokens: int = 16  # Maximum notes per output line.


def action_token(action: Action | None) -> str:
    """Format one action: 4, -4, -3'', 8', 4o, 7o, or ? for a gap."""
    if action is None:
        return "?"
    if action.technique in (Technique.OVERBLOW, Technique.OVERDRAW):
        return f"{action.hole}o"
    prefix = "-" if action.technique in (Technique.DRAW, Technique.DRAW_BEND) else ""
    return prefix + str(action.hole) + "'" * action.bend_semitones


def _ordinal(position: int) -> str:
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(position, "th")
    return f"{position}{suffix}"


def _summary(arrangement: Arrangement) -> str:
    stats = arrangement.stats
    return (
        f"{stats.get('bends', 0)} bends, {stats.get('overblows', 0)} over-notes, "
        f"{stats.get('unplayable', 0)} unplayable, {stats.get('jumps', 0)} jumps"
    )


def render_text(
    melody: Melody,
    arrangement: Arrangement,
    style: str = "standard",
    *,
    options: TextOptions | None = None,
    alternatives: Sequence[Arrangement] = (),
) -> str:
    """Render a header and tab lines, split at long rests or the configured token limit."""
    options = options or TextOptions()
    validate_melody(melody)
    if style != "standard":
        raise ValueError("only the standard tab style is currently supported")
    if len(melody.notes) != len(arrangement.actions):
        raise ValueError("arrangement must have one action per melody note")
    if (
        type(options.max_tokens) is not int
        or options.max_tokens < 1
        or not isfinite(options.phrase_rest)
        or options.phrase_rest < 0
    ):
        raise ValueError("max_tokens must be positive and phrase_rest finite and nonnegative")
    key = estimate_key(melody)
    label = "provided" if melody.key_estimate is not None else "estimated"
    lines = [
        f"Song key: {KEY_NAMES[key.tonic]} {key.mode} ({label})",
        f"Harp: {KEY_NAMES[arrangement.harp_key]}, {_ordinal(arrangement.position)} position",
        f"Transpose: {arrangement.transpose:+d} semitones",
        f"Difficulty: {_summary(arrangement)}; cost {arrangement.cost:.2f}",
    ]
    for alternative in alternatives:
        lines.append(
            f"Alternative: {KEY_NAMES[alternative.harp_key]}, "
            f"{_ordinal(alternative.position)} position, "
            f"{alternative.transpose:+d} semitones; {_summary(alternative)}"
        )
    lines.append("")
    threshold = max(options.phrase_rest, 60 / melody.tempo_bpm if melody.tempo_bpm else 0)
    phrase: list[str] = []
    previous_end = 0.0
    for note, action in zip(melody.notes, arrangement.actions, strict=True):
        if phrase and (note.start - previous_end > threshold or len(phrase) >= options.max_tokens):
            lines.append(" ".join(phrase))
            phrase = []
        phrase.append(action_token(action))
        previous_end = note.start + note.duration
    if phrase:
        lines.append(" ".join(phrase))
    return "\n".join(lines) + "\n"
