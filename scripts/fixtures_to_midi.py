"""Convert hand-written melody fixtures to MIDI without copying external material."""

import json
from pathlib import Path

import mido

from harptab.models import Melody
from harptab.render.text import KEY_NAMES


def write_midi(melody: Melody, path: Path) -> None:
    """Write a fixture with constant tempo, preserving note times to MIDI tick precision."""
    tempo = mido.bpm2tempo(melody.tempo_bpm or 120)
    midi = mido.MidiFile(ticks_per_beat=960)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Melody"))
    track.append(mido.MetaMessage("set_tempo", tempo=tempo))
    if melody.key_estimate:
        key = KEY_NAMES[melody.key_estimate.tonic]
        if melody.key_estimate.mode == "minor":
            key = {"Db": "C#", "Eb": "D#", "Ab": "G#", "Bb": "Bb"}.get(key, key) + "m"
        track.append(mido.MetaMessage("key_signature", key=key))
    events = []
    for note in melody.notes:
        start = round(mido.second2tick(note.start, midi.ticks_per_beat, tempo))
        end = round(mido.second2tick(note.start + note.duration, midi.ticks_per_beat, tempo))
        events.extend([(start, 1, note.pitch), (end, 0, note.pitch)])
    previous = 0
    for tick, on, pitch in sorted(events):
        track.append(
            mido.Message(
                "note_on" if on else "note_off",
                note=pitch,
                velocity=80 if on else 0,
                time=tick - previous,
            )
        )
        previous = tick
    midi.save(str(path))


def main() -> None:
    """Generate ignored MIDI files alongside the versioned melody fixtures."""
    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    output = fixtures / "midi"
    output.mkdir(exist_ok=True)
    for path in sorted((fixtures / "melodies").glob("*.melody.json")):
        tune = Melody.from_dict(json.loads(path.read_text(encoding="utf-8")))
        target = output / path.name.replace(".melody.json", ".mid")
        write_midi(tune, target)
        print(target)


if __name__ == "__main__":
    main()
