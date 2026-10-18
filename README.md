# harptab

Arrange a melody for a ten-hole diatonic harmonica. The working implementation
accepts melody JSON and MIDI, recommends a harp, and prints tabs or structured JSON.
MusicXML is available with an optional dependency. The audio extra transcribes
clean solo recordings with pYIN. An optional Demucs stage isolates source stems
before tracking; accuracy on a full mix depends on the material. Practice guides
explain each hole/breath/bend with timestamps, and a WAV preview lets you hear the notes.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run harptab tests/fixtures/melodies/ode_to_joy.melody.json --harps C
uv run harptab arrange song.mid --harps C,G,A --alternatives 2
uv run harptab arrange song.mid --harps C --mode practice --format json -o tab.json
```

The Ode to Joy example prints:

```text
Song key: C major (provided)
Harp: C, 1st position
Transpose: +0 semitones
Difficulty: 0 bends, 0 over-notes, 0 unplayable, 0 jumps; cost 1.93

5 5 -5 6 6 -5 5 -4 4 4 -4 5 5 -4 -4
```

Play-along is the default and preserves every source pitch. Practice may transpose
the melody, including octave moves; the header and JSON report the total semitone shift.
Overblows and overdraws require `--overblows`. Use `--skill beginner|intermediate|advanced`
to adjust difficulty costs. A `?` preserves the place of an unplayable note.

For MusicXML, use `uv run --extra musicxml harptab score.musicxml`; `.xml` and `.mxl`
are also supported.

## Audio input

Use an isolated voice, solo instrument, or melody stem:

```sh
uv run --extra audio harptab solo.wav --no-separate --harps C,G,A
uv run --extra audio harptab transcribe solo.wav --no-separate -o solo.melody.json
uv run harptab arrange solo.melody.json --harps C --mode practice
```

The intermediate JSON can be edited before arrangement. Loading and tracking progress
goes to stderr, leaving JSON on stdout valid. WAV and FLAC decode directly; codecs
unsupported by the installed soundfile library require `ffmpeg` on PATH (for example,
some M4A files). Audio is converted to mono at 22,050 Hz for pYIN or 16,000 Hz for CREPE.

The current tracker covers C2–C7 by default. The Python API exposes `PyinParams` and
`SegmentParams` for frequency range, time resolution, tuning correction, confidence,
and note-length thresholds. For example:

```python
from harptab.pipeline import transcribe_audio
from harptab.transcribe.pitch import PyinParams

melody = transcribe_audio(
    "solo.wav", no_separate=True, pitch_params=PyinParams(fmin=100, fmax=1500)
)
```

For a mix, install the separation extra and choose the melody's stem:

```sh
uv run --extra separation harptab transcribe song.wav --stem vocals -o song.melody.json
uv run --extra separation harptab instrumental.wav --stem other --device cpu --harps C,G,A
```

The default stem is `vocals`; `other`, `bass` and `drums` are also available.
Demucs separates instrument categories, so `other` may still contain chords and
several instruments. For an already isolated source, keep using `--no-separate`.
The optional `crepe` pitch backend provides a second tracker:

```sh
uv run --extra crepe harptab transcribe solo.wav --no-separate --pitch-backend crepe -o melody.json
uv run --extra crepe --extra separation harptab transcribe song.wav --pitch-backend crepe --stem vocals --start 30 --duration 20 -o melody.json
```

`--start` and `--duration` select an audio excerpt in seconds before separation and
tracking. Note timestamps remain relative to the original file. Start with a short
section where the melody is clear. Omit these flags to process the entire recording.

CREPE uses [torchcrepe](https://github.com/maxrmorrison/torchcrepe), whose wheel includes
the pretrained weights. `CrepeParams` controls model size (`full`/`tiny`), batch size,
CPU/CUDA selection, frequency range and confidence gating in the Python API.
Its upper frequency limit is 2006 Hz, slightly below C7. Each tracker owns its model;
Viterbi decoding spans inference batches and has no random pitch dithering.
CREPE confidence is periodicity, not a calibrated probability of a correct note.
pYIN remains the default: CREPE improves many backing cases but regresses on one
wide-range vibrato fixture and fails an additional original backing probe. See the
[CREPE comparison](eval/results/2026-10-11-crepe.md) and
[original melody probe](eval/results/2026-10-11-crepe-probe.md).

Repeated notes need an audible gap to be distinguished
from one sustained note; dense backing, vocal ornaments and large tuning offsets
can cause errors. The first audio operation may take longer while numerical kernels compile.

Separation uses [demucs-infer](https://github.com/openmirlab/demucs-infer), an inference
fork compatible with current Python/PyTorch, and downloads official Demucs weights
on first use. `--device auto` selects CUDA when the installed PyTorch supports it,
otherwise CPU. `--separation-model htdemucs_ft` selects the slower fine-tuned model;
`htdemucs` is the default. CPU inference has been checked locally; CUDA is not yet tested.

Stems and model weights live in the platform's `harptab` user cache directory.
Use `--cache-dir PATH` to choose another directory or `--no-cache` to bypass stem
storage/reuse (downloaded weights remain cached). Cache keys include file and decoded
audio hashes, sample rate, model, stem, inference options and dependency versions.
Cache hits avoid importing Torch or loading the model. The library exposes the same
options through `SeparationParams` and `transcribe_audio(..., separation_params=...)`.

## Try a song and get practice instructions

The workflow is ready for **short, reviewed song trials**. Start with a 20–30-second
section where the melody is clear. A full mix can still produce incorrect or missing
notes; listen to the preview and compare it with the recording.

For example, extract the vocal melody from 30–50 seconds into a song:

```sh
uv run --extra crepe --extra separation harptab transcribe song.mp3 --pitch-backend crepe --stem vocals --start 30 --duration 20 -o melody.json --preview detected.wav
uv run harptab arrange melody.json --harps C --format practice --preview practice.wav -o practice.md
```

Use the keys printed on your own harmonicas in `--harps`. For an instrumental lead,
try `--stem other`; for an isolated voice or solo instrument, use `--no-separate`.
If the preview has mistakes, edit the note pitches/times in `melody.json` and rerun
the arrangement command. Unplayable notes remain `?` and silent gaps in the preview.
`--mode practice` may shift the melody to fit; the guide clearly reports that shift.

The Markdown guide breaks the tune into short phrases, spells out blow/draw and
bends, and flags low-confidence notes for review. Times refer to the original recording.
`--practice-speed 0.5` gives half-speed hold/rest times and playback without lowering
the pitch; the default is 0.75. WAV previews start at the first displayed note and
play a bundled bank of real harmonica recordings from
[basic-harmonica](https://github.com/michael02022/basic-harmonica), released under
CC0. Each note uses a nearby recorded sample, adjusted to the target pitch; long
notes repeat its sustain loop. Bends sound at their target pitches without a
bend-in gesture, and the bank does not distinguish blow/draw timbres. Use
`--preview-voice sine` for the original plain reference tones, or
`PreviewOptions(voice="sine")` in the Python API. Both voices work without audio
extras or downloads. Sample provenance and conversion details are in
[the sample credits](src/harptab/assets/harmonica/SOURCE.md).
The preview limit is five minutes at the selected
practice speed; choose a shorter excerpt for longer material.

Try the included [Ode to Joy practice guide](docs/examples/ode-to-joy-practice.md), or generate it:

```sh
uv run harptab tests/fixtures/melodies/ode_to_joy.melody.json --harps C --format practice --preview practice.wav -o practice.md
```

## Chords and fuller arrangements

Chord mode preserves simultaneous source notes and assigns playable groups of
2-4 adjacent holes on the same breath. `[1 2 3]` means blow all three holes together;
`[-4 -5 -6]` means draw all three together. Single-note mode remains the default.

```sh
uv run harptab score.mid --chords --harps C,G,A --format practice --preview chords.wav -o chords.md
uv run harptab score.json --chords --harps G --format json -o chord-tab.json
uv run --extra audio harptab reviewed-melody.json --harmony-audio instrumental-stem.wav --harps G,A,C --format json -o candidates.json
uv run harptab candidates.json --chords --harps G --format practice --preview practice.wav -o practice.md
```

`--harmony-audio` uses an isolated instrumental stem with the **same time origin** as
the reviewed melody. It proposes persistent lower notes during those events and
keeps their timing and melody pitches. Review/edit the resulting `score.events`
before practicing: spectral peaks can be overtones, bleed, or backing layers.
This does not establish reliable automatic chord recognition in arbitrary mixes.

MIDI chord mode combines non-percussion tracks; MusicXML combines pitched parts.
The highest pitch is the default melody. Score JSON can set `melody_pitch` for each
event to protect a different voice. Unsupported harmony is listed as omitted;
unsupported melody remains a rest. Search favors playable melody before harmony
coverage. The best harp for a single melody can differ from the best harp for chords.

```python
from harptab import ChordEvent, ChordScore, search_chords
from harptab.playback import preview_chords_wav
from harptab.render.chords import render_chord_practice

score = ChordScore([ChordEvent((60, 64, 67), start=0, duration=0.5)])
best = search_chords(score, harps=[0])[0]
print(render_chord_practice(score, best))  # [1 2 3], simultaneously
preview_chords_wav("chord.wav", score, best)
```

Chord playback uses the same recorded harmonica bank, mixes the assigned notes,
and limits peaks without clipping. Bent/over-notes are supported as individual
notes, with over-notes requiring `--overblows`. Chord bends, tongue-blocked splits,
and independent legato voices are not yet modeled; symbolic voice changes
rearticulate the block. The core and chord playback need no audio extras.

## Single-note library API

```python
from harptab import KeyEstimate, Melody, NoteEvent, search
from harptab.render.text import render_text

melody = Melody(
    notes=[NoteEvent(72, 0.0, 0.5), NoteEvent(74, 0.5, 0.5), NoteEvent(76, 1.0, 0.5)],
    key_estimate=KeyEstimate(0, "major", 1.0),
)
best = search(melody, harps=[0])[0]  # C harmonica; keys are pitch classes 0..11
print(render_text(melody, best))
```

`assign(melody, HarmonicaModel(0))` fixes the instrument. `Melody.to_dict()` and
`Melody.from_dict()` provide the hand-editable intermediate JSON format. Rendered JSON
contains `melody` and `arrangement` and can also be fed back to `harptab arrange`.
All times are seconds; pitches are MIDI integers. Notes must be sorted and monophonic.

## Live microphone practice

Save a reviewed arrangement as JSON, then launch the local listener:

```sh
uv run --no-sync harptab arrange tests/fixtures/melodies/ode_to_joy.melody.json --harps C --format json -o practice.json
uv run --no-sync harptab listen practice.json
```

For existing A and G versions, pass both arranged JSON files:

```sh
uv run --no-sync harptab listen a-arrangement.json g-arrangement.json
```

The browser opens at `http://127.0.0.1:8765/`. Select the arrangement, click
**Start practice** and allow microphone access. A large three-second count-in leads
into the phrase. The display shows upcoming notes, a moving play position, hold/rest
durations, target notes/chords, the notes it hears, sharp/flat cents and hole/breath
guidance. **Start microphone** also works independently for checking your pitch.
**Save guide** downloads the selected harp's guide at 50% speed.

The **light-up harmonica** shows the exact holes from the selected arrangement,
including every hole in a chord. Its label tells you to inhale or exhale and calls
out bends and over-notes. The lights turn off for rests and breath breaks. Song
names come from the source filename when available; loading another arrangement
changes the notes, holes, timing and score targets without changing application code.

During a run, the matched/missed/skipped counter and marked phrase steps show your
progress. Afterward, **Your last run** gives a percentage and per-step review with
detected extra notes, missing chord notes, tuning or input problems. Select a tab
in the review to retry from that step. Results stay visible during replay and loops.
The score is the share of playable steps with a sustained pitch match; skipped
steps earn no credit, and unavailable notes are excluded. It measures detected
pitch matches, not rhythm, tone or overall musicianship. Demo results are labeled.

- **Follow along** (default): follow the arrangement's timing and rests at 50%,
  75% or full speed. Misses and extra detected notes do not stop the phrase, and
  pitches stay unchanged. Only matched steps receive credit.
- **Step by step:** hold the correct pitches, then briefly pause your breath to
  move through the phrase. Repeated notes require separate breaths.
- Select any step or use Previous/Next to move without stopping a running session.
  Restart returns to the beginning; Loop repeats with a fresh count-in. The
  **visual demo** uses explicitly labeled simulated input without a microphone.

**Review what you played** keeps your actual microphone recording and the full
detected-note timeline for each new practice take. Press **Listen to my take**, drag
the timeline, or jump to a step to compare target notes with the notes detected at
that moment. **Finish & review** saves a partial take; Pause also saves a take, and
continuing begins another. Loop iterations are kept separately. The recording
includes the count-in, but playback initially seeks to the first target.

Takes survive song changes and remain in the current tab until you delete them,
close it, or reload. **Download audio** keeps the original microphone recording;
**Download notes** exports the full take's timing and note measurements as JSON.
Recordings are prepared as seekable WAV audio when browser decoding is available,
with the browser's original format retained as a fallback. Starting only the microphone and
the visual demo do not record takes. Playing a take stops microphone capture so
the replay cannot be scored as new playing. If recording fails, the UI identifies
the take as timeline-only. Past audio from before recording was implemented cannot
be recovered.

Audio stays in your browser and is never uploaded. Stop the microphone to release
it; hiding the tab saves the current take and stops capture. Use headphones for a
backing track. The noise gate and cents tolerance are adjustable. The detector
smooths the note display and briefly retains it as **Last heard** during dropouts;
retained readings do not count toward practice matches. The input readout explains
whether the sound is below the noise gate or its pitch is unclear. The detector
hears pitches, not which hole or technique you used. Chord estimates can confuse
overtones, octave chords, echoes and quiet reeds; use Next when a chord won't lock.
This first version has automated signal tests but still needs physical microphone
trials in real rooms.

**Detected-note details** shows measured frequency, relative level and possible
fingerings on the selected harp. For example, Ab4/G#4 is hole 3 draw on an A harp;
its presence could indicate an adjacent reed sounding or a detection error.
**Save note diagnostics** downloads six seconds of note measurements for debugging.
This is a local JSON download, with no recorded audio or upload.

Only existing rendered melody/chord JSON is accepted. Raw melodies/scores must be
arranged first with `--format json`; chord input also uses `--chords`. Targets
reflect the actual voicing and transposition, not omitted source harmony.
No audio extras or runtime Node installation are required. `--no-browser` prints
the URL without opening it, `--port` selects another port, and Ctrl+C stops the
server. If microphone access is unavailable, open the loopback URL in a normal
browser tab; browser capture requires a secure context, including localhost.
See [the microphone API documentation](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia#privacy_and_security).

## Development

```sh
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
node --test tests/listener/*.test.mjs
uv build
uv run python scripts/fixtures_to_midi.py
uv run --extra evaluation pytest -m audio
uv run --extra evaluation python -m eval
uv run --extra separation --extra evaluation python -m eval.separation --benchmark-seconds 180
```

Listener development tests use Node 22+; runtime microphone processing uses the
browser's built-in audio APIs. The core has no audio dependencies. Tests include instrument/position coverage,
Viterbi comparisons against exhaustive paths, search invariants, MIDI tempo changes,
exact public-domain fixture tabs, and CLI tests. Audio tests use synthesized signals.
The evaluation harness writes a dated report under `eval/results/` with note F1,
pitch accuracy, and tab accuracy for clean, vibrato, noise and backing variants.
Without evaluation dependencies it reports N/A for audio and still checks core tabs.
The separate audio CI job runs on manual workflow dispatch; its optional `separation`
checkbox also runs CPU model integration tests. Model-download tests are
opt-in: set `HARPTAB_TEST_DEMUCS=1`, then run
`uv run --extra separation pytest -m separation`. Set `HARPTAB_DEMUCS_CACHE` to reuse
a model cache across those tests. Ordinary tests never download models.

The [2026-10-11 baseline](eval/results/2026-10-11.md) achieved note F1 of 1.000 and
100% tab accuracy on all seven clean, vibrato, and noise fixtures. Backing variants
scored 0.000–0.133 note F1. Separation is measured independently with the comparison
harness above; synthetic results do not establish accuracy on real-world mixes.
The [separation comparison](eval/results/2026-10-11-separation.md) found a small mean
pitch-accuracy gain (30.5% to 32.1%), with two regressions. Six of seven backed
fixtures still have zero note F1. Full-mix transcription remains experimental.
A three-minute synthesized file took 221 seconds to separate on a Ryzen 7 5800H CPU
with four OpenMP threads; a cached read took 0.062 seconds. These timings exclude
pitch tracking and the initial model download.

Read the [implementation review and plan](docs/IMPLEMENTATION_PLAN.md),
[architecture](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md), and
[harmonica reference](docs/harmonica-reference.md). Coding guidance is in
[docs/AGENTS.md](docs/AGENTS.md). Key estimation and difficulty
defaults are heuristics. Synthetic audio results do not establish accuracy on real
singing or full mixes.
