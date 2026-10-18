"""MIDI loading with a global tempo map and channel-aware note pairing."""

from bisect import bisect_right
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import mido

from harptab.ingest.chords import chord_events
from harptab.ingest.reduce import choose_track, skyline
from harptab.models import ChordScore, KeyEstimate, Melody, NoteEvent
from harptab.validation import validate_melody, validate_score


def load_midi(path: str | Path) -> Melody:
    """Load a type 0/1 MIDI file, excluding percussion and reducing the selected track."""
    result = _load_midi(path, chords=False)
    assert isinstance(result, Melody)
    return result


def load_midi_score(path: str | Path) -> ChordScore:
    """Preserve all simultaneous pitches across non-percussion MIDI tracks/channels."""
    result = _load_midi(path, chords=True)
    assert isinstance(result, ChordScore)
    return result


def _load_midi(path: str | Path, *, chords: bool) -> Melody | ChordScore:
    midi = mido.MidiFile(str(path))
    if midi.type == 2:
        raise ValueError("MIDI type 2 has independent timelines; export as type 0 or 1")
    if midi.ticks_per_beat <= 0:
        raise ValueError("SMPTE MIDI timing is not supported; export with ticks per beat")
    events: list[tuple[int, int, int, Any]] = []
    for track_id, track in enumerate(midi.tracks):
        tick = 0
        for sequence, message in enumerate(track):
            tick += message.time
            events.append((tick, track_id, sequence, message))
    events.sort(key=lambda event: event[:3])
    tempo_ticks = [0]
    tempo_seconds = [0.0]
    tempos = [500000]
    key_estimate = None
    for tick, _, _, message in events:
        if message.type == "set_tempo":
            if message.tempo <= 0:
                raise ValueError("MIDI tempo must be positive")
            elapsed = (tick - tempo_ticks[-1]) * tempos[-1] / (midi.ticks_per_beat * 1_000_000)
            tempo_seconds.append(tempo_seconds[-1] + elapsed)
            tempo_ticks.append(tick)
            tempos.append(message.tempo)
        elif message.type == "key_signature" and key_estimate is None:
            name = message.key
            minor = name.endswith("m")
            name = name.removesuffix("m")
            naturals = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
            tonic = (naturals[name[0]] + name.count("#") - name.count("b")) % 12
            key_estimate = KeyEstimate(tonic, "minor" if minor else "major", 1.0)

    def seconds(tick: int) -> float:
        index = bisect_right(tempo_ticks, tick) - 1
        return float(
            tempo_seconds[index]
            + (tick - tempo_ticks[index]) * tempos[index] / (midi.ticks_per_beat * 1_000_000)
        )

    # Channel separation also handles multitimbral type-0 files.
    active: dict[tuple[int, int, int], deque[int]] = defaultdict(deque)
    tracks: dict[tuple[int, int], list[NoteEvent]] = defaultdict(list)
    ends: dict[int, int] = {}
    names: dict[int, str] = {}
    for tick, track_id, _, message in events:
        ends[track_id] = tick
        if message.type == "track_name":
            names[track_id] = message.name
        if message.type not in ("note_on", "note_off") or message.channel == 9:
            continue
        identity = (track_id, message.channel, message.note)
        if message.type == "note_on" and message.velocity > 0:
            active[identity].append(tick)
        elif active[identity]:
            start = seconds(active[identity].popleft())
            duration = seconds(tick) - start
            if duration > 0:
                tracks[(track_id, message.channel)].append(NoteEvent(message.note, start, duration))
    for (track_id, channel, pitch), starts in active.items():
        for tick in starts:
            start, end = seconds(tick), seconds(ends[track_id])
            if end > start:
                tracks[(track_id, channel)].append(NoteEvent(pitch, start, end - start))
    chosen = choose_track(
        [(names.get(track, ""), notes) for (track, _), notes in sorted(tracks.items())]
    )
    last_tick = max(ends.values(), default=0)
    beats = [seconds(tick) for tick in range(0, last_tick + 1, midi.ticks_per_beat)]
    initial_tempo = tempos[bisect_right(tempo_ticks, 0) - 1]
    if chords:
        score = ChordScore(
            chord_events([n for track in tracks.values() for n in track]),
            60_000_000 / initial_tempo,
            beats,
            key_estimate,
            str(path),
        )
        validate_score(score)
        return score
    melody = Melody(skyline(chosen), 60_000_000 / initial_tempo, beats, key_estimate, str(path))
    validate_melody(melody)
    return melody
