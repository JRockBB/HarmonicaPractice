# harptab

Arrange a melody for a ten-hole diatonic harmonica. The working implementation
accepts melody JSON and MIDI, recommends a harp, and prints tabs or structured JSON.
MusicXML is available with an optional dependency. The audio extra transcribes
clean solo recordings with pYIN. An optional Demucs stage isolates source stems
before tracking; accuracy on a full mix depends on the material.

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
some M4A files). Audio is converted to mono at 22,050 Hz.

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
Only the `pyin` pitch backend is available. Repeated notes need an audible gap to be distinguished
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

## Library API

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

## Development

```sh
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
uv run python scripts/fixtures_to_midi.py
uv run --extra evaluation pytest -m audio
uv run --extra evaluation python -m eval
uv run --extra separation --extra evaluation python -m eval.separation --benchmark-seconds 180
```

The core has no audio dependencies. Tests include instrument/position coverage,
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
