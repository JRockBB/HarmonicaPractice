"""Readable, timed practice instructions using only the shared music contracts."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite

from harptab.models import Action, Arrangement, Melody, NoteEvent, Technique
from harptab.render.text import KEY_NAMES, action_token, render_text
from harptab.validation import validate_melody


@dataclass(frozen=True)
class PracticeOptions:
    phrase_notes: int = 8  # Maximum notes in one practice phrase.
    phrase_rest: float = 0.6  # Seconds of silence that start another phrase.
    speed: float = 0.75  # Practice speed relative to the original recording.
    review_confidence: float = 0.75  # Flag notes below this backend-specific confidence.
    minimum_rest: float = 0.02  # Shortest gap worth showing as an explicit rest, seconds.

    def __post_init__(self) -> None:
        if type(self.phrase_notes) is not int or self.phrase_notes < 1:
            raise ValueError("phrase_notes must be a positive integer")
        for name in ("phrase_rest", "minimum_rest"):
            value = getattr(self, name)
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not isfinite(self.speed) or not 0 < self.speed <= 1:
            raise ValueError("practice speed must be in (0, 1]")
        if not isfinite(self.review_confidence) or not 0 <= self.review_confidence <= 1:
            raise ValueError("review_confidence must be in [0, 1]")


def action_instruction(action: Action | None) -> str:
    """Explain the hole, breath direction and technique of a single tab action."""
    if action is None:
        return "Unplayable on this harp; leave a rest"
    if type(action.hole) is not int or not 1 <= action.hole <= 10:
        raise ValueError("action hole must be in 1..10")
    if type(action.bend_semitones) is not int or action.bend_semitones < 0:
        raise ValueError("bend_semitones must be a nonnegative integer")
    if action.technique in (Technique.BLOW, Technique.DRAW):
        if action.bend_semitones:
            raise ValueError("unbent actions cannot have bend_semitones")
        verb = "Blow (exhale)" if action.technique == Technique.BLOW else "Draw (inhale)"
        return f"{verb} through hole {action.hole}"
    if action.technique in (Technique.DRAW_BEND, Technique.BLOW_BEND):
        if not action.bend_semitones:
            raise ValueError("a bend action requires a positive bend_semitones")
        verb = "Draw (inhale)" if action.technique == Technique.DRAW_BEND else "Blow (exhale)"
        unit = "semitone" if action.bend_semitones == 1 else "semitones"
        return f"{verb} hole {action.hole}; bend down {action.bend_semitones} {unit}"
    if action.technique in (Technique.OVERBLOW, Technique.OVERDRAW):
        if action.bend_semitones:
            raise ValueError("over-notes cannot have bend_semitones")
        verb = (
            "Overblow (exhale)" if action.technique == Technique.OVERBLOW else "Overdraw (inhale)"
        )
        return f"{verb} hole {action.hole} — advanced technique"
    raise ValueError("unknown action technique")


def _timestamp(seconds: float) -> str:
    hundredths = round(seconds * 100)
    minutes, remainder = divmod(hundredths, 6000)
    return f"{minutes:02d}:{remainder / 100:05.2f}"


def _note_name(pitch: int) -> str:
    return f"{KEY_NAMES[pitch % 12]}{pitch // 12 - 1}"


def render_practice(
    melody: Melody,
    arrangement: Arrangement,
    *,
    options: PracticeOptions | None = None,
    alternatives: Sequence[Arrangement] = (),
) -> str:
    """Render a Markdown practice guide with source timestamps and slowed hold durations.

    Phrase grouping preserves every note and explicit gaps. Transposed versions are
    labeled, unplayable notes remain rests, and low-confidence notes are flagged for review.
    """
    validate_melody(melody)
    if not melody.notes:
        raise ValueError("a practice guide requires melody notes")
    p = options or PracticeOptions()
    if len(melody.notes) != len(arrangement.actions):
        raise ValueError("arrangement must have one action per melody note")
    for note, action in zip(melody.notes, arrangement.actions, strict=True):
        action_instruction(action)
        if action is not None and action.pitch != note.pitch + arrangement.transpose:
            raise ValueError("action pitch must match the transposed melody note")
    playable = sum(action is not None for action in arrangement.actions)
    uncertain = sum(note.confidence < p.review_confidence for note in melody.notes)
    bends = sum(
        action is not None and action.technique in (Technique.DRAW_BEND, Technique.BLOW_BEND)
        for action in arrangement.actions
    )
    overnotes = sum(
        action is not None and action.technique in (Technique.OVERBLOW, Technique.OVERDRAW)
        for action in arrangement.actions
    )
    lines = [
        "# Harmonica practice guide",
        "",
        f"Use a **{KEY_NAMES[arrangement.harp_key]} harmonica**. "
        f"{playable} of {len(melody.notes)} notes are playable in this arrangement.",
        "",
        "```text",
        render_text(melody, arrangement, alternatives=alternatives).rstrip(),
        "```",
        "",
    ]
    if arrangement.transpose:
        lines += [
            f"This practice version shifts the melody by **{arrangement.transpose:+d} semitones**. "
            "Shift the backing by the same amount for an exact pitch match.",
            "",
        ]
    else:
        lines += ["This arrangement preserves the source pitches for playing along.", ""]
    if bends or overnotes:
        lines += [
            f"Technique work: **{bends} bent notes** and **{overnotes} over-notes**. "
            "Practice those notes individually before connecting the phrase.",
            "",
        ]
    if playable < len(melody.notes):
        lines += [
            "Notes marked `?` have no playable action in this arrangement. Keep their timing "
            "as rests, or choose a different harp/practice transposition.",
            "",
        ]
    lines += [
        "## How to practice",
        "",
        "1. Locate holes 1–10, from the low-pitched end to the high-pitched end.",
        "2. Play one hole at a time. `4` means blow hole 4; `-4` means draw hole 4.",
        "3. Each apostrophe means one semitone of bend. An `o` marks an advanced over-note; "
        "the instruction column gives its breath direction.",
        f"4. Start at **{p.speed:.0%} speed**. Use the hold times below and repeat each phrase "
        "until you can connect the notes smoothly.",
        "5. Increase your speed gradually, then join neighboring phrases.",
        "",
        "Source timestamps point into the original file. Hold/rest durations below are "
        f"scaled for {p.speed:.0%} practice speed. They are timing estimates, not beat notation.",
        "",
    ]
    if uncertain:
        lines += [
            f"**Review {uncertain} note(s)** marked “Check pitch/timing” against the recording. "
            "Confidence flags are review aids; an unflagged note can still be wrong.",
            "",
        ]
    lines += [
        "If this melody came from audio, check these short phrases against the recording "
        "before practicing them. Edit the melody JSON and arrange it again "
        "when corrections are needed.",
        "",
    ]
    phrases: list[list[tuple[NoteEvent, Action | None]]] = []
    previous_end = 0.0
    for note, action in zip(melody.notes, arrangement.actions, strict=True):
        if (
            not phrases
            or len(phrases[-1]) >= p.phrase_notes
            or note.start - previous_end > p.phrase_rest
        ):
            phrases.append([])
        phrases[-1].append((note, action))
        previous_end = note.start + note.duration
    for number, phrase in enumerate(phrases, 1):
        first, last = phrase[0][0], phrase[-1][0]
        lines += [
            f"## Phrase {number}: {_timestamp(first.start)}–"
            f"{_timestamp(last.start + last.duration)}",
            "",
            " ".join(f"`{action_token(action)}`" for _, action in phrase),
            "",
            "| At (source) | Tab | Play | Hold/rest | Note | Review |",
            "| --- | --- | --- | ---: | --- | --- |",
        ]
        previous_end = first.start
        for note, action in phrase:
            gap = note.start - previous_end
            if gap > p.minimum_rest:
                lines.append(
                    f"| {_timestamp(previous_end)} | — | Rest | {gap / p.speed:.2f}s | — | |"
                )
            label = "Check pitch/timing" if note.confidence < p.review_confidence else ""
            lines.append(
                f"| {_timestamp(note.start)} | `{action_token(action)}` | "
                f"{action_instruction(action)} | {note.duration / p.speed:.2f}s | "
                f"{_note_name(note.pitch + arrangement.transpose)} | {label} |"
            )
            previous_end = note.start + note.duration
        lines.append("")
        if number < len(phrases):
            gap = phrases[number][0][0].start - previous_end
            if gap > p.minimum_rest:
                lines += [f"Rest for **{gap / p.speed:.2f}s** before the next phrase.", ""]
    return "\n".join(lines)
