"""Validation at input boundaries, without coercing musical data."""

from math import isfinite

from harptab.models import ChordArrangement, ChordScore, Melody, NoteEvent, Technique, Voicing


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


def validate_score(score: ChordScore) -> None:
    """Validate pitches and preserve the melody's timing and metadata rules."""
    for event in score.events:
        if not event.pitches or any(type(p) is not int or not 0 <= p <= 127 for p in event.pitches):
            raise ValueError("chord pitches must be nonempty integer MIDI pitches in 0..127")
        if tuple(sorted(set(event.pitches))) != event.pitches:
            raise ValueError("chord pitches must be unique and sorted")
        if event.melody_pitch is not None and (
            type(event.melody_pitch) is not int or event.melody_pitch not in event.pitches
        ):
            raise ValueError("melody_pitch must be one of the chord pitches")
    validate_melody(
        Melody(
            [NoteEvent(e.lead, e.start, e.duration, e.confidence) for e in score.events],
            score.tempo_bpm,
            score.beats,
            score.key_estimate,
            score.source,
        )
    )


def validate_voicing(voicing: Voicing, harp_key: int) -> None:
    """Reject invented reeds, mixed breaths, hole gaps and multi-hole bends."""
    from harptab.core.instrument import HarmonicaModel

    harp = HarmonicaModel(harp_key)
    actions = voicing.actions
    if not actions:
        raise ValueError("a voicing must contain at least one action")
    for action in actions:
        if any(
            type(value) is not int for value in (action.hole, action.pitch, action.bend_semitones)
        ):
            raise ValueError("voicing hole, pitch and bend must be integers")
        if action not in harp.actions_for_pitch(action.pitch):
            raise ValueError("voicing action does not produce that pitch on this harp")
    if len(actions) == 1:
        return
    holes = [a.hole for a in actions]
    if len(actions) > 4 or holes != list(range(holes[0], holes[0] + len(holes))):
        raise ValueError("block chords require 2-4 contiguous holes in ascending order")
    if actions[0].technique not in (Technique.BLOW, Technique.DRAW) or any(
        a.technique != actions[0].technique for a in actions
    ):
        raise ValueError("block chords require unbent notes with the same breath direction")


def validate_chord_arrangement(score: ChordScore, arrangement: ChordArrangement) -> None:
    """Validate a playable reduction; missing harmony remains explicit in the score."""
    validate_score(score)
    validate_key(arrangement.harp_key)
    if type(arrangement.transpose) is not int:
        raise ValueError("transpose must be an integer number of semitones")
    if len(score.events) != len(arrangement.voicings):
        raise ValueError("arrangement must have one voicing per chord event")
    for event, voicing in zip(score.events, arrangement.voicings, strict=True):
        if voicing is None:
            continue
        validate_voicing(voicing, arrangement.harp_key)
        played = {a.pitch for a in voicing.actions}
        requested = {p + arrangement.transpose for p in event.pitches}
        if not played <= requested or event.lead + arrangement.transpose not in played:
            raise ValueError("voicing must retain the melody and use only requested pitches")
