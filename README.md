# harptab

Arrange a melody for a ten-hole diatonic harmonica. The working implementation
accepts melody JSON and MIDI, recommends a harp, and prints tabs or structured JSON.
MusicXML is available with an optional dependency. The audio extra transcribes
clean solo recordings with pYIN. Source separation for full mixes is still planned.

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

`--no-separate` is required until source separation is implemented. Only the `pyin`
pitch backend is available. Repeated notes need an audible gap to be distinguished
from one sustained note; dense backing, vocal ornaments and large tuning offsets
can cause errors. The first audio operation may take longer while numerical kernels compile.

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
```

The core has no audio dependencies. Tests include instrument/position coverage,
Viterbi comparisons against exhaustive paths, search invariants, MIDI tempo changes,
exact public-domain fixture tabs, and CLI tests. Audio tests use synthesized signals.
The evaluation harness writes a dated report under `eval/results/` with note F1,
pitch accuracy, and tab accuracy for clean, vibrato, noise and backing variants.
Without evaluation dependencies it reports N/A for audio and still checks core tabs.
The separate audio CI job runs on manual workflow dispatch.

The [2026-10-11 baseline](eval/results/2026-10-11.md) achieved note F1 of 1.000 and
100% tab accuracy on all seven clean, vibrato, and noise fixtures. Backing variants
scored 0.000–0.133 note F1, so full mixes remain unsupported without separation.

Read the [implementation review and plan](docs/IMPLEMENTATION_PLAN.md),
[architecture](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md), and
[harmonica reference](docs/harmonica-reference.md). Coding guidance is in
[docs/AGENTS.md](docs/AGENTS.md). Key estimation and difficulty
defaults are heuristics. Synthetic audio results do not establish accuracy on real
singing or full mixes.
