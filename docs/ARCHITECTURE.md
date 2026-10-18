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

The original single-note path meets at `Melody`. The optional harmony path meets at
`ChordScore`, with simultaneous pitches in each event. Both are dependency-free.
The arrangement core must never import audio libraries.

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
    practice.py        # timed Markdown practice instructions
  playback.py          # standard-library harmonica/sine WAV export
  playback_samples.py  # standard-library sampler for bundled CC0 harmonica recordings
  assets/harmonica/    # recorded notes, sustain/tuning metadata and public-domain dedication
  cli.py               # `harptab` command
  listener.py          # loopback-only live-practice server and arrangement adapter
  assets/listener/     # browser microphone, pitch detector, progression and visual feedback
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

### Chord contract extension (2026-10-13)

The user's request to fix missing chord support authorizes an additive contract
extension. Existing `NoteEvent`, `Melody`, `Action` and `Arrangement` fields and JSON
remain unchanged. A chord score is explicit; monophonic input is not automatically
reharmonized. All consumers of the new types are implemented together.

```python
@dataclass(frozen=True)
class ChordEvent:
    pitches: tuple[int, ...]  # sorted, unique simultaneous MIDI pitches
    start: float
    duration: float
    confidence: float = 1.0
    melody_pitch: int | None = None  # None means highest pitch; otherwise must be in pitches


@dataclass
class ChordScore:
    events: list[ChordEvent]  # sorted, non-overlapping; individual events can contain one note
    tempo_bpm: float | None = None
    beats: list[float] | None = None
    key_estimate: KeyEstimate | None = None
    source: str = ""


@dataclass(frozen=True)
class Voicing:
    actions: tuple[Action, ...]  # one action, or 2-4 adjacent unbent same-breath holes


@dataclass(frozen=True)
class ChordArrangement:
    harp_key: int
    position: int
    transpose: int
    voicings: list[Voicing | None]  # one per event; None means the melody cannot be played
    cost: float
    stats: dict[str, int]
```

`ChordScore` and `ChordArrangement` round-trip through JSON. Event `pitches` and
voicing `actions` are arrays; rendered JSON uses `score`, `arrangement`, `alternatives`.
`validate_score` validates every pitch and retains the melody timeline rules.
`validate_chord_arrangement` rejects false reeds, mixed-breath chords, hole gaps,
multi-hole bends, added pitches, and missing designated melody notes.

`core/chords.py` enumerates source-supported block voicings and assigns a path with
Viterbi. Single-note fallback retains the melody. Missing harmony is penalized and
reported as `omitted_tones` and `incomplete_chords`; it never becomes a wrong chord
or a transposed substitute. Search prioritizes melody coverage, then cost. Default
play-along still uses zero transposition. Split/tongue-blocked voicings are deferred.

`ingest/chords.py` groups active pitches at symbolic note boundaries. Chord-mode
MIDI preserves all non-percussion tracks/channels; MusicXML preserves pitched parts.
Voice changes become block events, so previews rearticulate when a voicing changes;
independent legato voices are not modeled. The default skyline melody path is retained.

`transcribe/harmony.py` optionally adds lower harmony candidates around a reviewed
melody using persistent spectral peaks in a full-length, aligned instrumental stem.
It does not add events, extend durations, or infer the song's harmony from the harp.
Overtones, backing layers, bleed and decays remain ambiguous; this is an assisted,
reviewable step, not unattended polyphonic transcription. It inherits the melody's
confidence; that field is not a calibrated estimate of chord correctness.

`render/chords.py` adds bracketed simultaneous tabs, breath instructions, scaled
timing/rests and explicit omissions. `preview_chords_wav` mixes only assigned reeds
with recorded samples or sine references, preserving speed-independent pitch and
silent gaps. Equal-power voice balancing and a global peak limit avoid clipping.
It models simultaneous notes, not acoustic reed interaction. Arrangement, rendering,
and playback remain usable without numerical/audio extras.

CLI `--chords` accepts score JSON, melody JSON, MIDI or MusicXML. `--harmony-audio`
implies chord mode and requires reviewed melody JSON plus an audio stem covering
the original source timestamps. Raw audio can first use the existing transcription
and review workflow. Input, harmony source, output and preview cannot alias.

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

Practice output adds explicit hole, breath and bend instructions, short phrases,
source timestamps, slowed hold/rest durations and confidence-review markers.
It preserves unplayable gaps and labels transpositions. Practice WAV export
uses the existing note times and arranged pitches, without audio dependencies.
The default harmonica voice plays bundled CC0 instrument recordings. Original
key regions and tuning corrections select the source sample; windowed-sinc
resampling sets the target pitch and sample rate. Embedded sustain-loop markers
extend held notes, and releases stay inside the note boundaries. A sine reference
voice remains selectable. Neither voice changes the tab's target pitches or rest
timing; the preview does not estimate a beat grid or model a player's bending
gesture. Sample caches belong to one export, and playback never downloads assets.

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

## Live practice listener

`harptab listen arrangement.json [another.json]` serves a local browser application
on IPv4 loopback. It accepts existing rendered melody or chord arrangements and
validates their reeds before creating display targets. Targets use the arrangement's
actual sounding pitches, including its transposition and omitted harmony. Original
source seconds are retained; the practice clock begins at the first event. Shared
music contracts are unchanged. This user-authorized Phase 4 pass coordinates WP9,
WP10, packaging and CI.

Microphone acquisition uses browser `getUserMedia`; capture begins only on a user
action. Starting practice also records that take locally for user-requested review.
Audio is never sent to the server or monitored live to speakers; starting the
microphone alone does not record. Playback of a saved take stops microphone capture.
The server exposes only bundled static files and the selected sessions, with no
directory browsing or write/upload route. It rejects non-loopback Host headers.
Microphone tracks close on Stop, navigation, hidden tabs, and canceled requests,
including requests that finish after cancellation.

The browser detector analyzes 8192-sample Hann-windowed frames, using an FFT,
interpolated spectral peaks, a configurable noise gate, tonal-energy rejection and
harmonic suppression. Detection is independent of the target. It estimates up to
four pitches; matching requires all arranged pitches within the cents tolerance
and no extra detected pitches. Clipping prevents match credit. Chord estimates
cannot reliably distinguish octave reeds from overtones, missing fundamentals,
backing audio, room echoes or unevenly voiced chords. This is practice feedback,
not proof of correct embouchure, hole selection or breath technique.

Vibrato peaks belonging to the same MIDI note are consolidated before harmonic
rejection, retaining the strongest peak's measured frequency/cents. Harmonic
rejection allows 60 cents of spectral spread. An independent voice must reach
18% of the strongest remaining fundamental's amplitude; this floor is applied
after harmonic removal so a reed with a strong overtone still keeps its quieter
fundamental. These target-independent filters reduce duplicate notes, moving
overtones and faint background pitches. They can miss a very quiet chord reed;
audible wrong notes above the floor still appear and prevent a match.

The note/cents display takes a three-frame median for the same detected note set
and retains the last reading for up to one second through missing frames. Retained
readings are explicitly labeled `Last heard`; live detections alone drive scoring
and the six-second pitch trail. The chart keeps historical pitches in its vertical
range after detection drops. The default noise gate is -50 dB, and the input readout
distinguishes quiet input, unclear pitch and clipping. Stopping capture clears the
retained display immediately.

Detected-note details show measured Hz, relative spectral amplitude and possible
fingerings derived from `HarmonicaModel` for the selected harp. These describe
ways to play a pitch, not proof of which reeds produced a microphone measurement.
An explicit Save note diagnostics button downloads the last six seconds of
note/frequency/cents/amplitude, input RMS and expected-pitch measurements as JSON.
It exports no audio and sends nothing to the server. This supports diagnosis of
real-room errors without blacklisting a particular note or changing the target.

Start practice acquires the microphone and begins the session in one action.
The default Follow along mode uses a monotonic clock, visible three-second count-in,
source durations/rests and selected speed. Detection errors never block its clock;
matches alone receive credit. A forward-looking note timeline, upcoming tab,
hold/rest countdown and phrase progress make the timing visible. Step by step mode
requires a stable match and a short quiet breath break before the next step,
protecting repeated notes from advancing on one sustained sound. Manual selection
and Previous/Next preserve running state and earned matches; Restart clears them.
Unplayable events stay visible; they require manual skipping in step-by-step mode.
The listener's presentation payload includes the selected voicing's hole, technique,
bend depth and pitch for each action. A ten-hole diagram renders these actions
directly, including simultaneous chords and explicit advanced techniques, and goes
dark during rests, breath breaks and completion. It does not infer target holes
from microphone pitches. Session titles use the source basename with the arrangement
filename as fallback. The shared arrangement schemas are unchanged.

Per-step observations record match counts, dominant failure categories and detected
extra/missing pitches. A completed run reports the percentage of playable steps
with sustained matches, separately counts misses/skips, and excludes unplayable
events. Count-ins, rests, pauses and held display readings are not scored; gaps
between observations longer than 250 ms break the sustained-match timer. Results
describe listener observations, with rhythm and tone grading explicitly excluded.
The last completed report remains visible across restart/loop, while new runs get
fresh counters. Changing arrangements clears the previous report, and simulated
input is labeled in both live counts and saved-in-memory results.

`takes.mjs` captures each real microphone practice take with browser MediaRecorder,
negotiating a supported MIME type. Finalization waits for the final dataavailable
and stop events; asynchronous callbacks own their take so overlapping finalization
and a new loop cannot mix recordings. Each take also retains every raw pitch frame
with elapsed recording time, target, step and count-in/play/rest phase, independently
of the rolling six-second live history. Pauses, early finish, restart, mode/speed
changes, device stop and hidden tabs finalize partial takes; continuing starts a new
take. Simulated input never creates a microphone recording.

`review.mjs` provides local audio playback/download, full-take note comparison,
scrubbing, step jumps and notes JSON export. When available, OfflineAudioContext decodes the complete take
to PCM WAV with explicit sample rate/data length for seeking; conversion failure
retains the native recording and displays a fallback notice. This uses the recorded
samples and performs no synthesis. See the browser
[audio decoding API](https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/decodeAudioData).
The same recording clock drives the comparison cursor; gaps in analysis do not
fabricate held notes. Browser encoding
and input latency are not calibrated for fine rhythm assessment. Recordings remain
in memory across loops and arrangement changes until deleted or the tab reloads;
download is the explicit persistence mechanism. Unsupported/failed recording is
labeled, with measured note history still reviewable. Blob media playback is allowed
by CSP while the server remains read-only and has no audio upload route. See the
[MediaRecorder API](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder).
The UI offers a clearly labeled simulated-input demo and a downloadable guide.
No audio extras, Node runtime or internet connection are needed to run the app;
Node is used only for detector, progression and UI-controller tests.

## Open questions

- **Melody vs. riff.** For some songs the recognizable line is a guitar riff, not the vocal. v1 assumes vocals; let the user pick the stem.
- **Sections.** Auto-detecting verse and chorus would make long tabs readable. Defer; maybe use repetition detection on the note sequence.
- **Bad transcription UX.** Transcription will make mistakes. A simple editable intermediate (`harptab transcribe song.mp3 -o song.melody.json`, edit, then `harptab arrange song.melody.json`) lets users fix it by hand.
- **Port the core.** If you still want Julia, `core/` is the natural piece to port, behind the same JSON melody format.
