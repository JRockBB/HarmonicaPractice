"""Input dispatch and optional audio transcription with source separation."""

import json
from collections.abc import Callable
from dataclasses import replace
from math import isfinite
from pathlib import Path

from harptab.models import Melody
from harptab.transcribe.crepe import CrepeParams
from harptab.transcribe.pitch import PyinParams, get_tracker
from harptab.transcribe.segment import SegmentParams, segment
from harptab.transcribe.separate import SeparationParams
from harptab.validation import validate_melody

AUDIO_SUFFIXES = frozenset((".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aiff"))


def transcribe_audio(
    path: str | Path,
    *,
    pitch_backend: str = "pyin",
    pitch_params: PyinParams | CrepeParams | None = None,
    segment_params: SegmentParams | None = None,
    no_separate: bool = False,
    stem: str = "vocals",
    separation_params: SeparationParams | None = None,
    start: float = 0.0,
    duration: float | None = None,
    progress: Callable[[str], None] | None = None,
) -> Melody:
    """Transcribe audio, isolating a stem unless ``no_separate=True``.

    Progress messages go to the supplied callback, leaving library and JSON output quiet.
    ``start`` and ``duration`` select an excerpt in seconds; returned note times
    still refer to the original recording.
    """
    from harptab.transcribe.load import load_audio

    if not isfinite(start) or start < 0:
        raise ValueError("excerpt start must be finite and nonnegative, in seconds")
    if duration is not None and (not isfinite(duration) or duration <= 0):
        raise ValueError("excerpt duration must be finite and positive, in seconds")
    params = pitch_params or (CrepeParams() if pitch_backend == "crepe" else PyinParams())
    tracker = get_tracker(pitch_backend, params)
    if progress:
        progress("Loading audio...")
    try:
        audio = load_audio(path, params.sample_rate)
    except ImportError as error:
        if no_separate:
            raise
        raise ImportError(
            "Audio with source separation requires: pip install 'harptab[separation]'. "
            "For a solo source, install 'harptab[audio]' and use --no-separate."
        ) from error
    if start >= len(audio) / params.sample_rate:
        raise ValueError("excerpt start is beyond the end of the recording")
    offset = round(start * params.sample_rate)
    if offset >= len(audio):
        raise ValueError("excerpt start is beyond the end of the recording")
    end = len(audio)
    if duration is not None and duration < (len(audio) - offset) / params.sample_rate:
        length = round(duration * params.sample_rate)
        if length < 1:
            raise ValueError("excerpt duration must contain at least one sample")
        end = offset + length
    if offset or duration is not None:
        audio = audio[offset:end]
        if progress:
            progress(
                f"Selected {offset / params.sample_rate:.2f}s to "
                f"{(offset + len(audio)) / params.sample_rate:.2f}s..."
            )
    if not no_separate:
        from harptab.transcribe.separate import file_digest, separate

        audio = separate(
            audio,
            params.sample_rate,
            stem,
            params=separation_params,
            source_hash=file_digest(path),
            progress=progress,
        )
    if progress:
        progress(f"Tracking pitch with {'CREPE' if pitch_backend == 'crepe' else 'pYIN'}...")
    track = tracker.track(audio, params.sample_rate)
    if progress:
        progress("Segmenting notes...")
    excerpt_length = len(audio) / params.sample_rate
    notes = [
        replace(
            note,
            start=note.start + offset / params.sample_rate,
            duration=min(note.duration, excerpt_length - note.start),
        )
        for note in segment(track, segment_params)
        if note.start < excerpt_length
    ]
    melody = Melody(notes, source=str(path))
    validate_melody(melody)
    return melody


def load_melody(
    path: str | Path,
    *,
    no_separate: bool = False,
    pitch_backend: str = "pyin",
    stem: str = "vocals",
    separation_params: SeparationParams | None = None,
    start: float = 0.0,
    duration: float | None = None,
    progress: Callable[[str], None] | None = None,
) -> Melody:
    """Read melody JSON, MIDI, optional MusicXML, or transcribe an audio file."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"input file does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix not in AUDIO_SUFFIXES and (start != 0 or duration is not None):
        raise ValueError("excerpt start/duration options apply only to audio inputs")
    if suffix in (".mid", ".midi"):
        from harptab.ingest.midi import load_midi

        return load_midi(path)
    if suffix in (".xml", ".musicxml", ".mxl"):
        from harptab.ingest.musicxml import load_musicxml

        return load_musicxml(path)
    if suffix in AUDIO_SUFFIXES:
        return transcribe_audio(
            path,
            no_separate=no_separate,
            pitch_backend=pitch_backend,
            stem=stem,
            separation_params=separation_params,
            start=start,
            duration=duration,
            progress=progress,
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
