from math import nan, pi, sin

import pytest

from harptab.models import Melody
from harptab.transcribe.pitch import PitchTrack
from harptab.transcribe.segment import SegmentParams, segment
from harptab.validation import validate_melody


def track(pitches: list[float | None], hop: float = 0.01) -> PitchTrack:
    return PitchTrack(
        [i * hop for i in range(len(pitches))],
        [nan if p is None else 440 * 2 ** ((p - 69) / 12) for p in pitches],
        [0.0 if p is None else 0.95 for p in pitches],
    )


def test_pitch_changes_and_repeated_notes_across_rests() -> None:
    notes = segment(track([60] * 40 + [62] * 40 + [None] * 10 + [62] * 40))
    assert [n.pitch for n in notes] == [60, 62, 62]
    assert [n.start for n in notes] == pytest.approx([0, 0.4, 0.9])
    assert [n.duration for n in notes] == pytest.approx([0.4, 0.4, 0.4])
    validate_melody(Melody(notes))


@pytest.mark.parametrize("phase", [0, pi / 2, pi, 3 * pi / 2])
def test_vibrato_stays_one_note(phase: float) -> None:
    contour = [69 + 0.5 * sin(2 * pi * 5 * i * 0.01 + phase) for i in range(100)]
    notes = segment(track(contour))
    assert len(notes) == 1
    assert notes[0].pitch == 69


def test_tuning_offset_metadata_and_isolated_octave_change() -> None:
    notes = segment(track([60.35] * 40 + [72.35] * 40))
    assert [n.pitch for n in notes] == [60, 72]
    assert [n.cents_offset for n in notes] == pytest.approx([35, 35])


def test_onset_scoop_absorbed_and_short_notes_dropped() -> None:
    contour = [67] * 6 + [69] * 40 + [None] * 10 + [72] * 4
    notes = segment(track(contour))
    assert len(notes) == 1
    assert notes[0].pitch == 69
    assert notes[0].start == 0


def test_short_dropout_bridged_but_real_gap_preserved() -> None:
    notes = segment(track([60] * 20 + [None] + [60] * 20 + [None] * 5 + [60] * 20))
    assert len(notes) == 2
    assert notes[0].duration == pytest.approx(0.41)
    assert notes[1].start == pytest.approx(0.46)


def test_short_pitch_glitch_and_low_confidence() -> None:
    assert len(segment(track([60] * 30 + [72] * 2 + [60] * 30))) == 1
    contour = track([60] * 20)
    assert segment(PitchTrack(contour.times, contour.f0_hz, [0.1] * 20)) == []
    assert segment(PitchTrack([], [], [])) == []
    assert segment(track([60])) == []
    assert segment(track([None] * 20)) == []


@pytest.mark.parametrize(
    "contour",
    [
        PitchTrack([0, 0.1], [440], [1, 1]),
        PitchTrack([0.1, 0], [440, 440], [1, 1]),
        PitchTrack([0, 0.1], [440, float("inf")], [1, 1]),
        PitchTrack([0, 0.1], [440, 440], [1, nan]),
    ],
)
def test_invalid_tracks(contour: PitchTrack) -> None:
    with pytest.raises(ValueError):
        segment(contour)


@pytest.mark.parametrize(
    "params",
    [
        SegmentParams(min_duration=0),
        SegmentParams(median_frames=2),
        SegmentParams(bridge_gap=-1),
        SegmentParams(min_confidence=2),
    ],
)
def test_invalid_parameters(params: SegmentParams) -> None:
    with pytest.raises(ValueError):
        segment(track([60] * 20), params)
