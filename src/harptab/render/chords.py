"""Chord tabs, explicit reductions and timed multi-hole playing instructions."""

import json
from collections.abc import Sequence

from harptab.models import ChordArrangement, ChordEvent, ChordScore, Technique, Voicing
from harptab.render.practice import PracticeOptions, _note_name, _timestamp, action_instruction
from harptab.render.text import KEY_NAMES, action_token
from harptab.validation import validate_chord_arrangement


def voicing_token(voicing: Voicing | None) -> str:
    """Brackets mean simultaneous notes, e.g. ``[-4 -5 -6]`` is one draw chord."""
    if voicing is None:
        return "?"
    tokens = [action_token(a) for a in voicing.actions]
    return tokens[0] if len(tokens) == 1 else "[" + " ".join(tokens) + "]"


def voicing_instruction(voicing: Voicing | None) -> str:
    if voicing is None:
        return "Melody unavailable on this harp; rest"
    if len(voicing.actions) == 1:
        return action_instruction(voicing.actions[0])
    verb = "Blow (exhale)" if voicing.actions[0].technique == Technique.BLOW else "Draw (inhale)"
    return f"{verb} through holes " + ", ".join(str(a.hole) for a in voicing.actions) + " together"


def omitted_pitches(event: ChordEvent, voicing: Voicing | None, transpose: int) -> list[int]:
    played = {a.pitch for a in voicing.actions} if voicing else set()
    return [p + transpose for p in event.pitches if p + transpose not in played]


def render_chord_text(
    score: ChordScore,
    arrangement: ChordArrangement,
    *,
    alternatives: Sequence[ChordArrangement] = (),
) -> str:
    """Render multi-hole tabs, and identify every unsupported source chord tone."""
    validate_chord_arrangement(score, arrangement)
    lines = [
        f"Harp: {KEY_NAMES[arrangement.harp_key]}",
        f"Transpose: {arrangement.transpose:+d} semitones",
        "Brackets = play these holes together on one breath.",
        " ".join(voicing_token(v) for v in arrangement.voicings),
    ]
    for event, voice in zip(score.events, arrangement.voicings, strict=True):
        omitted = omitted_pitches(event, voice, arrangement.transpose)
        if omitted:
            lines.append(
                f"{_timestamp(event.start)}: omitted " + ", ".join(map(_note_name, omitted))
            )
    for other in alternatives:
        validate_chord_arrangement(score, other)
        lines.append(
            f"Alternative: {KEY_NAMES[other.harp_key]}, shift {other.transpose:+d}, "
            f"{other.stats['chords']} chord events, {other.stats['unplayable']} melody gaps, "
            f"{other.stats['omitted_tones']} omitted tones"
        )
    return "\n".join(lines) + "\n"


def render_chord_json(
    score: ChordScore,
    arrangement: ChordArrangement,
    *,
    alternatives: Sequence[ChordArrangement] = (),
) -> str:
    validate_chord_arrangement(score, arrangement)
    for other in alternatives:
        validate_chord_arrangement(score, other)
    return (
        json.dumps(
            {
                "score": score.to_dict(),
                "arrangement": arrangement.to_dict(),
                "alternatives": [a.to_dict() for a in alternatives],
            },
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def render_chord_practice(
    score: ChordScore,
    arrangement: ChordArrangement,
    *,
    options: PracticeOptions | None = None,
    alternatives: Sequence[ChordArrangement] = (),
) -> str:
    """Explain simultaneous holes and partial chords, preserving source timing and rests."""
    validate_chord_arrangement(score, arrangement)
    if not score.events:
        raise ValueError("a practice guide requires chord events")
    p = options or PracticeOptions()
    lines = [
        "# Harmonica chord practice",
        "",
        f"Use a **{KEY_NAMES[arrangement.harp_key]} harmonica**.",
        "",
        "```text",
        render_chord_text(score, arrangement, alternatives=alternatives).rstrip(),
        "```",
        "",
        "Play bracketed holes **together**, not one after another. "
        "These voicings use adjacent holes on the same breath; no tongue blocking is required.",
        "",
        "Only the notes listed as played are in the preview. Omitted harmony tones are "
        "shown explicitly; an unsupported melody becomes a rest.",
        "",
        f"Practice at **{p.speed:.0%} speed**. Source timestamps refer to the recording; "
        "hold/rest times below are scaled for practice.",
        "",
    ]
    if arrangement.transpose:
        lines += [
            f"This version shifts the source by **{arrangement.transpose:+d} semitones**; "
            "the original backing will not match its pitches.",
            "",
        ]
    else:
        lines += ["This arrangement preserves the selected source pitches.", ""]
    lines += [
        "| At (source) | Tab | Play | Hold/rest | Sounding pitches | Omitted / review |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    previous = score.events[0].start
    for event, voice in zip(score.events, arrangement.voicings, strict=True):
        if event.start - previous > p.minimum_rest:
            lines.append(
                f"| {_timestamp(previous)} | — | Rest | "
                f"{(event.start - previous) / p.speed:.2f}s | | |"
            )
        played = ", ".join(_note_name(a.pitch) for a in voice.actions) if voice else "—"
        missing = omitted_pitches(event, voice, arrangement.transpose)
        review = "Omitted: " + ", ".join(map(_note_name, missing)) if missing else ""
        if event.confidence < p.review_confidence:
            review += "; Check harmony/timing" if review else "Check harmony/timing"
        lines.append(
            f"| {_timestamp(event.start)} | `{voicing_token(voice)}` | "
            f"{voicing_instruction(voice)} | {event.duration / p.speed:.2f}s | "
            f"{played} | {review} |"
        )
        previous = event.start + event.duration
    return "\n".join(lines) + "\n"
