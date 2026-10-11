# Architecture

## Pipeline

```
 audio file ──► [1 load] ──► [2 separate] ──► [3 pitch track] ──► [4 segment] ──┐
                                                                                 │
 MIDI / MusicXML ──► [1b symbolic ingest] ──► [4b melody reduce] ────────────────┤
                                                                                 ▼
                                                                         Melody (NoteEvents)
                                                                                 │
                       ┌─────────────────────────────────────────────────────────┘
                       ▼
               [5 key & position search] ──► [6 hole assignment] ──► [7 render] ──► tab
                       ▲
               HarmonicaModel (instrument tables)
```

Stages 1–4 are **transcription**: audio in, melody out. They are heavy (ML models, ffmpeg, GPU optional) and imprecise.

Stages 5–7 are **arrangement**: melody in, tab out. They are pure Python, deterministic, fast, and fully unit-testable.

The two halves meet at one data type, `Melody`. Keeping them separated is the most important rule in the codebase: the arrangement core must never import audio libraries.

## Package layout

```
src/harptab/
  models.py            # shared dataclasses (the contracts below); no logic
  core/                # arrangement half: pure Python, no heavy deps
    instrument.py      # HarmonicaModel: note tables, bends, overblows, tunings
    positions.py       # key/position math
    search.py          # stage 5: pick harp key, position, octave, transposition
    assign.py          # stage 6: dynamic-programming hole assignment
    difficulty.py      # cost tables shared by search and assign
  transcribe/          # transcription half: optional heavy deps
    load.py            # stage 1: decode audio to mono float array
    separate.py        # stage 2: isolate vocals / lead (Demucs)
    pitch.py           # stage 3: frame-level f0 (pYIN, CREPE, basic-pitch backends)
    segment.py         # stage 4: f0 contour -> NoteEvents
    tempo.py           # beat/tempo estimate for rhythm display
  ingest/              # symbolic inputs
    midi.py
    musicxml.py
    reduce.py          # polyphonic -> single melody line
  render/
    text.py            # stage 7: plain-text tab
    json.py            # machine-readable output
  cli.py               # `harptab` command
tests/
  core/ transcribe/ ingest/ render/ e2e/
  fixtures/            # hand-written melodies, synthesized audio, NO commercial recordings
eval/                  # transcription accuracy harness (mir_eval)
```

Install extras: `pip install harptab` gives the core, symbolic ingest and rendering.
`pip install 'harptab[audio]'` adds clean-source transcription;
`pip install 'harptab[separation]'` adds Demucs source separation and the audio stack.
`pip install 'harptab[crepe]'` adds the optional neural pitch tracker and audio stack.

## Data contracts (`models.py`)

These are the interfaces between work packages. Changing them requires updating this file and every consumer in the same change.

```python
@dataclass(frozen=True)
class NoteEvent:
    pitch: int  # MIDI note number (60 = C4)
    start: float  # seconds
    duration: float  # seconds
    confidence: float = 1.0  # 0..1, from transcription; 1.0 for symbolic input
    cents_offset: float = 0.0  # mean deviation from equal temperament, informational


@dataclass
class Melody:
    notes: list[NoteEvent]  # monophonic, sorted by start, non-overlapping
    tempo_bpm: float | None = None
    beats: list[float] | None = None  # beat times in seconds
    key_estimate: KeyEstimate | None = None
    source: str = ""  # file name, for display


@dataclass(frozen=True)
class KeyEstimate:
    tonic: int  # pitch class 0..11 (0 = C)
    mode: str  # "major" | "minor"
    confidence: float


class Technique(Enum):
    BLOW = "blow"
    DRAW = "draw"
    DRAW_BEND = "draw_bend"
    BLOW_BEND = "blow_bend"
    OVERBLOW = "overblow"
    OVERDRAW = "overdraw"


@dataclass(frozen=True)
class Action:  # one physical way to make a pitch
    hole: int  # 1..10
    technique: Technique
    bend_semitones: int = 0  # 0 for unbent, 1..3 for bends
    pitch: int = 0  # resulting MIDI pitch


@dataclass(frozen=True)
class Arrangement:
    harp_key: int  # pitch class of the harmonica
    position: int  # 1..12
    transpose: int  # semitones applied to the song (0 in play-along mode)
    actions: list[Action | None]  # one per NoteEvent; None = unplayable, shown as a gap
    cost: float
    stats: dict[str, int]  # counts: bends, overblows, unplayable, jumps
```

## Stage notes

### 1. Load
Decode with `librosa.load` (ffmpeg via `audioread`/`soundfile`), mono, 22.05 kHz or 16 kHz depending on the pitch backend. Clear error if ffmpeg is missing.

### 2. Separate
The melody of most songs is the vocal line, which competes with guitars, keys and drums. Run Demucs to get a vocals stem and pitch-track that. Fallbacks:
- `--stem other` for instrumentals where the lead is not vocal.
- `--no-separate` for already-clean recordings (solo instrument, humming).

Separation is the slowest step. Cache stems on disk keyed by file hash.

### 3. Pitch track
Pluggable backends behind one interface `track(audio, sr) -> (times, f0_hz, voiced_prob)`:
- `pyin` (librosa): default, no ML weights, decent on clean vocals.
- `crepe` (torchcrepe): optional neural tracker, needs torch; measured against the same fixtures.
- `basic-pitch`: polyphonic note output, useful when separation fails; reduce afterwards.

### 4. Segment
Turn a frame-level f0 contour into notes. This is where most of the musical judgment lives:
- Convert Hz to fractional MIDI, median-filter.
- Split on unvoiced gaps and on pitch jumps larger than ~0.7 semitone that persist for more than a few frames.
- Treat vibrato (periodic ±0.5 semitone) as one note; take the median pitch.
- Treat slides and scoops at note onsets as ornaments, not notes.
- Drop notes shorter than a minimum (~80 ms, tunable) and low-confidence notes.
- Optionally snap onsets to the beat grid from `tempo.py`.

Singers drift off concert pitch. Estimate a global tuning offset (median cents deviation) and subtract it before rounding to semitones.

### 4b. Melody reduce (symbolic)
For multi-track MIDI: choose the track most likely to be the melody (highest mean pitch, most notes, track name hints like "melody", "vocal", "lead"), then apply "skyline" (highest note wins) to remove chords.

### 5. Key & position search
Search over:
- harp key: 12, or only the harps the user owns (`--harps C,G,A`)
- song transposition: 0 only in play-along mode; −6..+5 in practice mode
- octave shift: whole octaves that put the melody inside the harp's range

For each candidate, cost each note with its cheapest action (see `difficulty.py`); unplayable notes get a large penalty. Return the top N candidates, each with its stats, so the CLI can show alternatives ("A harp, 2nd position: 2 bends. D harp, 1st position: 0 bends but 3 notes out of range").

"Position" is derived from the harp key and the song key, not searched separately. It is reported because players think in positions.

Use the melody's own pitches for the search, not only the key estimate. Key detection is unreliable and the melody is what has to be playable.

### 6. Hole assignment
A pitch may be playable in more than one way (on a C harp, G4 is 2 draw or 3 blow; with overblows several more options appear). Choose the sequence of actions with a Viterbi pass:

- State: candidate action for note *i*.
- Node cost: technique cost from `difficulty.py`.
- Edge cost: hole distance, breath-direction change, entering or leaving a bend, plus a small preference for staying in the middle register.

The number of candidates per note is small (≤4), so this is trivially fast.

### 7. Render
Text format (see `harmonica-reference.md` for notation):
- Group notes into lines by phrase. A rest longer than a threshold or a beat-grid bar boundary starts a new line.
- Header with harp key, position, transposition, difficulty summary.
- Optional rhythm row under each line in a later phase.

JSON output is the `Arrangement` plus the `Melody`, for front ends.

## Difficulty model (`difficulty.py`)

One table, used by both search and assignment, so tuning it changes behavior consistently. Starting values (to be tuned against real tabs):

| Action | Cost |
|---|---|
| Blow / draw | 0 |
| Half-step bend | 1 |
| Whole-step bend | 2 |
| 1½-step bend (3 draw) | 3 |
| Blow bend (8–10) | 2 |
| Overblow / overdraw | 6 (disabled unless `--overblows`) |
| Unplayable note | 50 |
| Breath change | 0.2 |
| Hole jump | 0.3 per hole beyond 1 |

Expose a `--skill beginner|intermediate|advanced` flag that swaps cost tables (a beginner table makes bends expensive).

## Open questions

- **Melody vs. riff.** For some songs the recognizable line is a guitar riff, not the vocal. v1 assumes vocals; let the user pick the stem.
- **Sections.** Auto-detecting verse and chorus would make long tabs readable. Defer; maybe use repetition detection on the note sequence.
- **Bad transcription UX.** Transcription will make mistakes. A simple editable intermediate (`harptab transcribe song.mp3 -o song.melody.json`, edit, then `harptab arrange song.melody.json`) lets users fix it by hand.
- **Port the core.** If you still want Julia, `core/` is the natural piece to port, behind the same JSON melody format.
