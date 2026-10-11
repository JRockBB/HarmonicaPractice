from harptab.ingest.reduce import choose_track, skyline
from harptab.models import Melody, NoteEvent
from harptab.validation import validate_melody


def test_skyline_splits_and_resumes_underlying_note() -> None:
    result = skyline([NoteEvent(60, 0, 4), NoteEvent(72, 1, 1), NoteEvent(67, 1.5, 1.5)])
    assert result == [
        NoteEvent(60, 0, 1),
        NoteEvent(72, 1, 1),
        NoteEvent(67, 2, 1),
        NoteEvent(60, 3, 1),
    ]
    validate_melody(Melody(result))


def test_skyline_preserves_repeated_note_onsets_and_silence() -> None:
    notes = [NoteEvent(72, 0, 1), NoteEvent(72, 1, 1), NoteEvent(72, 3, 1)]
    assert skyline(notes) == notes
    assert skyline([]) == []


def test_track_hints_and_empty_tracks() -> None:
    lead = [NoteEvent(60, 0, 1)]
    assert (
        choose_track([("empty melody", []), ("Lead", lead), ("chords", [NoteEvent(84, 0, 1)])])
        == lead
    )
    assert choose_track([]) == []
