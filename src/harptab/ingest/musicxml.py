"""Optional MusicXML adapter, using music21's performed timing map."""

from pathlib import Path

from harptab.ingest.reduce import choose_track, skyline
from harptab.models import Melody, NoteEvent
from harptab.validation import validate_melody


def load_musicxml(path: str | Path) -> Melody:
    """Load MusicXML (including compressed MXL); install ``harptab[musicxml]`` first."""
    try:
        from music21 import converter
    except ImportError as error:
        raise ImportError("MusicXML input requires: pip install 'harptab[musicxml]'") from error
    score = converter.parse(str(path))
    tracks: list[tuple[str, list[NoteEvent]]] = []
    for part in score.parts or [score]:
        notes: list[NoteEvent] = []
        for event in part.flatten().secondsMap:
            element = event["element"]
            duration = float(event["durationSeconds"])
            if not getattr(element, "isNote", False) and not getattr(element, "isChord", False):
                continue
            if duration <= 0:
                continue
            for pitch in element.pitches:
                notes.append(NoteEvent(int(pitch.midi), float(event["offsetSeconds"]), duration))
        tracks.append((str(getattr(part, "partName", "") or ""), notes))
    marks = score.flatten().getElementsByClass("MetronomeMark")
    tempo = float(marks[0].getQuarterBPM()) if marks else 120.0
    melody = Melody(skyline(choose_track(tracks)), tempo_bpm=tempo, source=str(path))
    validate_melody(melody)
    return melody
