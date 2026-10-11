"""Input dispatch and clean-monophonic-audio transcription."""

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from harptab.models import Melody
from harptab.transcribe.pitch import PyinParams, get_tracker
from harptab.transcribe.segment import SegmentParams, segment
from harptab.validation import validate_melody

AUDIO_SUFFIXES = frozenset((".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aiff"))


def transcribe_audio(
    path: str | Path,
    *,
    pitch_backend: str = "pyin",
    pitch_params: PyinParams | None = None,
    segment_params: SegmentParams | None = None,
    no_separate: bool = False,
    progress: Callable[[str], None] | None = None,
) -> Melody:
    """Transcribe a clean mono source; explicitly opt out of pending source separation.

    Progress messages go to the supplied callback, leaving library and JSON output quiet.
    """
    if not no_separate:
        raise NotImplementedError(
            "Source separation is not implemented yet. For a solo instrument, voice or "
            "already isolated melody, use --no-separate (library: no_separate=True)."
        )
    from harptab.transcribe.load import load_audio

    params = pitch_params or PyinParams()
    tracker = get_tracker(pitch_backend, params)
    if progress:
        progress("Loading audio...")
    audio = load_audio(path, params.sample_rate)
    if progress:
        progress("Tracking pitch with pYIN...")
    track = tracker.track(audio, params.sample_rate)
    if progress:
        progress("Segmenting notes...")
    duration = len(audio) / params.sample_rate
    notes = [
        replace(note, duration=min(note.duration, duration - note.start))
        for note in segment(track, segment_params)
        if note.start < duration
    ]
    melody = Melody(notes, source=str(path))
    validate_melody(melody)
    return melody


def load_melody(
    path: str | Path,
    *,
    no_separate: bool = False,
    pitch_backend: str = "pyin",
    progress: Callable[[str], None] | None = None,
) -> Melody:
    """Read melody JSON, MIDI, optional MusicXML, or explicitly isolated audio."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"input file does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix in (".mid", ".midi"):
        from harptab.ingest.midi import load_midi

        return load_midi(path)
    if suffix in (".xml", ".musicxml", ".mxl"):
        from harptab.ingest.musicxml import load_musicxml

        return load_musicxml(path)
    if suffix in AUDIO_SUFFIXES:
        return transcribe_audio(
            path, no_separate=no_separate, pitch_backend=pitch_backend, progress=progress
        )
    if suffix != ".json":
        raise ValueError(f"unsupported file type: {suffix or '(no extension)'}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("melody JSON must contain an object")
    try:
        # Rendered JSON can be fed back to the arranger as well as standalone Melody JSON.
        melody = Melody.from_dict(data.get("melody", data))
        validate_melody(melody)
    except (TypeError, KeyError, AttributeError) as error:
        raise ValueError(f"invalid melody JSON: {error}") from error
    return melody
