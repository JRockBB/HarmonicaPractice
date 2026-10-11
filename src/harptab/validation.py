"""Validation at input boundaries, without coercing musical data."""

from math import isfinite

from harptab.models import Melody


def validate_key(key: int) -> None:
    """Require an integer pitch class in 0..11."""
    if type(key) is not int or not 0 <= key <= 11:
        raise ValueError("key must be an integer pitch class in 0..11")


def _finite(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")


def validate_melody(melody: Melody) -> None:
    """Require finite, sorted, non-overlapping notes and valid optional metadata."""
    previous_end = 0.0
    for note in melody.notes:
        if type(note.pitch) is not int or not 0 <= note.pitch <= 127:
            raise ValueError("pitch must be an integer MIDI note in 0..127")
        for name in ("start", "duration", "confidence", "cents_offset"):
            _finite(getattr(note, name), name)
        if note.start < 0 or note.duration <= 0:
            raise ValueError("note start must be nonnegative and duration must be positive")
        if note.start < previous_end - 1e-9:
            raise ValueError("melody notes must be sorted and non-overlapping")
        if not 0 <= note.confidence <= 1:
            raise ValueError("confidence must be in 0..1")
        previous_end = note.start + note.duration
        _finite(previous_end, "note end")
    if melody.tempo_bpm is not None:
        _finite(melody.tempo_bpm, "tempo_bpm")
        if melody.tempo_bpm <= 0:
            raise ValueError("tempo_bpm must be positive")
    if melody.beats is not None:
        previous = -1.0
        for beat in melody.beats:
            _finite(beat, "beat time")
            if beat < 0 or beat <= previous:
                raise ValueError("beats must be nonnegative and strictly increasing")
            previous = beat
    if melody.key_estimate is not None:
        key = melody.key_estimate
        validate_key(key.tonic)
        if key.mode not in ("major", "minor"):
            raise ValueError("key mode must be major or minor")
        _finite(key.confidence, "key confidence")
        if not 0 <= key.confidence <= 1:
            raise ValueError("key confidence must be in 0..1")
    if not isinstance(melody.source, str):
        raise ValueError("source must be a string")
