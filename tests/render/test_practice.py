import pytest

from harptab.core.assign import assign
from harptab.core.instrument import HarmonicaModel
from harptab.models import Action, Melody, NoteEvent, Technique
from harptab.render.practice import PracticeOptions, action_instruction, render_practice


@pytest.mark.parametrize(
    "action,instruction",
    [
        (Action(4, Technique.BLOW), "Blow (exhale) through hole 4"),
        (Action(4, Technique.DRAW), "Draw (inhale) through hole 4"),
        (Action(3, Technique.DRAW_BEND, 2), "Draw (inhale) hole 3; bend down 2 semitones"),
        (Action(10, Technique.BLOW_BEND, 1), "Blow (exhale) hole 10; bend down 1 semitone"),
        (Action(4, Technique.OVERBLOW), "Overblow (exhale) hole 4 — advanced technique"),
        (Action(7, Technique.OVERDRAW), "Overdraw (inhale) hole 7 — advanced technique"),
        (None, "Unplayable on this harp; leave a rest"),
    ],
)
def test_action_instructions(action: Action | None, instruction: str) -> None:
    assert action_instruction(action) == instruction


def test_guide_keeps_recording_time_and_scales_practice_duration() -> None:
    melody = Melody([NoteEvent(72, 30, 0.5), NoteEvent(74, 30.7, 0.3, confidence=0.6)])
    arrangement = assign(melody, HarmonicaModel(0))
    guide = render_practice(melody, arrangement, options=PracticeOptions(speed=0.5))
    assert "**C harmonica**" in guide
    assert "2 of 2 notes" in guide
    assert "## Phrase 1: 00:30.00–00:31.00" in guide
    assert "| 00:30.00 | `4` | Blow (exhale) through hole 4 | 1.00s | C5 |" in guide
    assert "| 00:30.50 | — | Rest | 0.40s |" in guide
    assert (
        "| 00:30.70 | `-4` | Draw (inhale) through hole 4 | 0.60s | D5 | Check pitch/timing |"
        in guide
    )
    assert "Review 1 note(s)" in guide


def test_phrases_preserve_notes_and_show_gaps_and_transposition() -> None:
    melody = Melody([NoteEvent(48, 0, 0.3), NoteEvent(60, 0.4, 0.3), NoteEvent(64, 2, 0.3)])
    arrangement = assign(melody, HarmonicaModel(0), transpose=12)
    guide = render_practice(melody, arrangement, options=PracticeOptions(phrase_notes=1))
    assert guide.count("## Phrase ") == 3
    assert "**+12 semitones**" in guide
    assert "Shift the backing by the same amount" in guide
    original = render_practice(melody, assign(melody, HarmonicaModel(0)))
    assert "2 of 3 notes" in original
    assert "Unplayable on this harp; leave a rest" in original
    assert "## Phrase 2: 00:02.00" in original
    assert "Rest for **1.73s** before the next phrase." in original


@pytest.mark.parametrize(
    "kwargs",
    [
        {"phrase_notes": 0},
        {"speed": 0},
        {"speed": 2},
        {"phrase_rest": -1},
        {"review_confidence": 2},
    ],
)
def test_invalid_practice_options(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        PracticeOptions(**kwargs)


def test_invalid_action_pitch_and_empty_guide_are_rejected() -> None:
    melody = Melody([NoteEvent(72, 0, 1)])
    wrong = assign(Melody([NoteEvent(74, 0, 1)]), HarmonicaModel(0))
    with pytest.raises(ValueError, match="action pitch"):
        render_practice(melody, wrong)
    with pytest.raises(ValueError, match="requires melody notes"):
        render_practice(Melody([]), assign(Melody([]), HarmonicaModel(0)))
