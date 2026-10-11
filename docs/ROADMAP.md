# Roadmap and work packages

The work is split into **work packages (WPs)** sized for one coding agent each. Each WP lists the files it owns, what it depends on, and when it counts as done. Agents should only edit files their WP owns; anything else goes in the PR description as a request.

The contracts in [`ARCHITECTURE.md`](ARCHITECTURE.md#data-contracts-modelspy) are what let WPs run in parallel. WP0 lands them first and nobody changes them without coordinating.

## Milestones

Implementation progress is recorded in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
The implementation covers WP0's foundation, WP1, WP2, WP5, WP6, WP7, WP8, WP9,
and the symbolic/audio portions of WP10. WP3 supports pYIN and optional CREPE;
basic-pitch remains pending. WP4 records synthesized transcription and separation
evaluations. Mixed recordings still require checking against the source. The practice
workflow includes timed instructions and reference-tone playback;
beat-grid rhythm notation and a self-service web uploader remain future work.
The original work-package descriptions below are retained
as the design backlog; "merged" is a milestone criterion, not a claim that commits
or pull requests have been created.

| Milestone | Meaning | Done when |
|---|---|---|
| **M0: Skeleton** | Repo builds, tests run, contracts exist | WP0 merged |
| **M1: Symbolic to tab** | A MIDI file of a simple melody becomes a correct tab | WP1, WP2, WP5, WP6, WP9 merged; e2e test passes on all fixtures |
| **M2: Audio to tab** | An audio recording becomes a usable tab | WP3, WP7, WP8, WP10 merged; eval baseline recorded |
| **M3: Usable tool** | Readable output, rhythm, hand-editable melody | Phase 4 items as chosen |

## Dependency graph

```
WP0 ──┬── WP1 ──┬── WP5 ──┐
      │         └── WP6 ──┤
      ├── WP2 ────────────┼── WP10 ── WP11
      ├── WP9 ────────────┤
      ├── WP3 ──┬── WP7 ──┤
      │         └── WP8 ──┘
      └── WP4 (needs WP3 to report numbers; harness can start immediately)
```

Phase 1 (after WP0): WP1, WP2, WP3, WP4, WP9 in parallel.
Phase 2: WP5, WP6, WP7, WP8 in parallel.
Phase 3: WP10, then WP11.

---

## Phase 0

### WP0 · Scaffolding and contracts
**Owns:** `pyproject.toml`, `src/harptab/models.py`, `src/harptab/__init__.py`, empty module stubs for every file in the package layout, `tests/conftest.py`, `tests/fixtures/`, CI config, `.gitignore`.

**Tasks**
- Project managed with `uv`; Python ≥ 3.11; `ruff` (lint + format), `pytest`, `mypy` (strict on `core/` and `models.py`).
- Optional extra `audio` for librosa, soundfile, torch, demucs, torchcrepe, basic-pitch. Core install must not pull any of these.
- Implement `models.py` exactly as specified in ARCHITECTURE.md, with `to_dict`/`from_dict` JSON round-tripping for `Melody` and `Arrangement`.
- Stub modules with function signatures and `raise NotImplementedError`, so later WPs fill bodies rather than invent APIs.
- Fixtures: 5–8 **public-domain** melodies as `tests/fixtures/melodies/*.melody.json`, each with a hand-checked expected tab for a stated harp and position in `*.expected.txt`. Mix of: major tune in 1st position, tune that needs 2nd position, one needing a bend, one with a wide range, one minor.
- CI: lint, type-check, core tests on every push. Audio tests marked `@pytest.mark.audio` and run in a separate, optional job.

**Done when** `uv run pytest` passes (stubs skipped), CI is green, and fixtures load into `Melody` objects.

---

## Phase 1

### WP1 · Instrument model and difficulty table
**Owns:** `core/instrument.py`, `core/positions.py`, `core/difficulty.py`, `tests/core/test_instrument.py`, `tests/core/test_positions.py`.

**Tasks**
- `HarmonicaModel(key, tuning="richter", octave_shift=0)` with `actions_for_pitch(pitch) -> list[Action]` and `range() -> (low, high)`.
- Derive bends, overblows and overdraws from the blow/draw tables using the gap rule in `harmonica-reference.md`. Do not hard-code per-key tables.
- Position helpers: `harp_for(song_key, position)`, `position_of(harp_key, song_key)`.
- `difficulty.py`: cost tables per skill level, `action_cost(action, skill)`, `transition_cost(prev, next, skill)`.
- Tuning registry with Richter implemented; leave a clear extension point for Country, Paddy Richter, Natural Minor.

**Done when** tests cover: the C table matches the reference exactly; every key is a correct shift; every bend and over-note listed in the reference is produced and nothing extra; position formula round-trips for all 12 × 12 combinations.

### WP2 · Symbolic ingest
**Owns:** `ingest/`, `tests/ingest/`.

**Tasks**
- `load_midi(path) -> Melody` using `mido` or `pretty_midi`; read tempo.
- `load_musicxml(path) -> Melody` via `music21` (optional dependency; clear error if missing).
- `reduce.py`: choose the melody track (heuristics in ARCHITECTURE.md), apply skyline, enforce the `Melody` invariants (sorted, monophonic, non-overlapping).
- A script `scripts/fixtures_to_midi.py` that writes each JSON fixture to MIDI, so ingest has real files to test against.

**Done when** every fixture round-trips JSON → MIDI → `Melody` with identical pitches and onsets within 10 ms, and a multi-track test file reduces to the intended melody.

### WP3 · Audio loading and pitch tracking
**Owns:** `transcribe/load.py`, `transcribe/pitch.py`, `tests/transcribe/test_load.py`, `tests/transcribe/test_pitch.py`.

**Tasks**
- `load_audio(path, sr) -> np.ndarray` (mono float32); helpful error when ffmpeg is missing.
- Backend interface `PitchTracker.track(audio, sr) -> PitchTrack(times, f0_hz, voiced_prob)`.
- Backends: `pyin` (default), `crepe` (torchcrepe), `basic_pitch` (returns note events; adapt to the same interface or a sibling one, document which).
- Tests on synthesized audio only: pure tones, a sine melody, a melody with vibrato, melody plus noise.

**Done when** on synthesized sine melodies the `pyin` backend's voiced-frame pitch is within 50 cents of truth for ≥ 95 % of voiced frames.

### WP4 · Evaluation harness
**Owns:** `eval/`.

**Tasks**
- Synthesize each fixture melody to audio (additive synth or FluidSynth with a free soundfont). Variants: clean, with noise, with a simple synthesized backing (chords + drums) to stress separation.
- Run the transcription pipeline (stages 1–4, whatever is implemented) and score with `mir_eval` (note onset/offset F-measure, raw pitch accuracy).
- Also score arrangement: percentage of tab tokens matching `*.expected.txt`.
- Output a markdown table to `eval/results/<date>.md` so progress is tracked over time.
- Optional: a `eval/local/` folder (git-ignored) where the user can drop their own recordings plus hand-made reference melodies.

**Done when** `uv run python -m eval` runs end to end with whichever stages exist and reports N/A for missing ones.

### WP9 · Rendering
**Owns:** `render/`, `tests/render/`.

**Tasks**
- `render_text(melody, arrangement, style="standard") -> str` using the notation in `harmonica-reference.md`.
- Header block: harp key, position, transposition, difficulty summary, alternatives if provided.
- Phrase line-breaking: rest longer than a threshold (default 0.6 s or one beat, whichever is larger) starts a new line; cap line length at ~16 tokens.
- `render_json(melody, arrangement) -> str`.

**Done when** snapshot tests pass on hand-built `Arrangement` objects covering every token type, including `?` for unplayable notes.

---

## Phase 2

### WP5 · Key, position and transposition search
**Owns:** `core/search.py`, `tests/core/test_search.py`.

**Depends on:** WP1.

**Tasks**
- `search(melody, mode="play_along"|"practice", harps=None, skill="intermediate", top_n=3) -> list[Arrangement]` (arrangements may carry `actions` filled in by calling WP6's assigner, or leave assignment to the caller; coordinate via the stub signature from WP0).
- Enumerate harp key × transposition × octave shift as described in ARCHITECTURE.md; cost each note by its cheapest action; rank.
- Tie-breakers: prefer 1st and 2nd position, prefer middle register, prefer no transposition.

**Done when** every fixture's expected harp and position is the top result, and a property test confirms play-along mode never transposes.

### WP6 · Hole assignment
**Owns:** `core/assign.py`, `tests/core/test_assign.py`.

**Depends on:** WP1.

**Tasks**
- `assign(melody, harp: HarmonicaModel, transpose: int, skill) -> Arrangement` with Viterbi over candidate actions using `difficulty.py`.
- Unplayable notes become `None` and do not break the path.
- Deterministic tie-breaking.

**Done when** fixture tabs match `*.expected.txt` exactly, and targeted tests show it picks 3 blow vs 2 draw sensibly depending on neighbors.

### WP7 · Note segmentation
**Owns:** `transcribe/segment.py`, `tests/transcribe/test_segment.py`.

**Depends on:** WP3.

**Tasks**
- `segment(track: PitchTrack, params) -> list[NoteEvent]` implementing the rules in ARCHITECTURE.md (tuning offset, vibrato merge, onset scoop removal, min duration, confidence).
- Expose parameters in a dataclass with documented defaults; WP4's harness should be able to sweep them.

**Done when** on synthesized fixtures (clean and vibrato variants) note F-measure (onset tolerance 50 ms, pitch exact) ≥ 0.9.

### WP8 · Source separation
**Owns:** `transcribe/separate.py`, `tests/transcribe/test_separate.py`.

**Depends on:** WP3.

**Tasks**
- `separate(audio, sr, stem="vocals") -> np.ndarray` using Demucs; CPU works, GPU used if present.
- On-disk cache keyed by (file hash, model, stem) in a user cache dir.
- `--no-separate` bypass.

**Done when** it runs on a 3-minute file on CPU within a documented time, the cache hit path is tested, and WP4 shows improved pitch accuracy on the "with backing" variants versus no separation.

---

## Phase 3

### WP10 · CLI and pipeline wiring
**Owns:** `cli.py`, `src/harptab/pipeline.py`, `tests/e2e/`.

**Depends on:** all Phase 1–2 WPs.

**Tasks**
- Commands:
  - `harptab <file>`: full pipeline, auto-detects audio vs MIDI/MusicXML.
  - `harptab transcribe <audio> -o song.melody.json`
  - `harptab arrange <melody.json|midi> [--harps C,G,A] [--mode practice] [--skill beginner]`
- Flags: `--stem`, `--no-separate`, `--pitch-backend`, `--overblows`, `--format text|json`, `--alternatives N`.
- Progress output for slow stages; friendly errors for missing extras (`pip install harptab[audio]`).

**Done when** e2e tests run the CLI on every fixture (MIDI and synthesized audio) and the output parses.

### WP11 · Baseline and polish
**Owns:** `eval/results/`, `README.md` usage section.

**Tasks**
- Run the eval harness, record baseline numbers.
- Tune segmentation and difficulty defaults against the fixtures; record before/after.
- Write the README usage section with real output.

---

## Phase 4: backlog (pick as needed)

- **Rhythm row** under each tab line (from beat grid: quarter, eighth, held).
- **Tempo and beat tracking** (`transcribe/tempo.py`) feeding phrase breaks and rhythm.
- **Alternate tunings** (Country, Paddy Richter, Natural Minor) via the WP1 registry.
- **Chromatic harmonica** model (12-hole, slide button) as a second `Instrument` implementation.
- **Section detection** (verse/chorus) from repetition in the note sequence.
- **Alternate tab styles** (`+4`, `4b`/`4d`).
- **Playback**: synthesize the tab back to audio so users can hear whether transcription was right.
- **Web UI**: upload a file, view tab, edit the melody in a piano roll, re-arrange.
- **Julia port of `core/`**, consuming the same melody JSON.

---

## Briefing an agent

Each agent gets this template, with the WP filled in:

```
You are working on harptab (see README.md). Read AGENTS.md, docs/ARCHITECTURE.md
and docs/harmonica-reference.md first.

Your task is WP<N> in docs/ROADMAP.md. Only edit the files that WP owns.
Do not change src/harptab/models.py; if you need a contract change, stop and
describe it in your final report instead.

Work in your own branch/worktree. Finish when the WP's "Done when" criteria pass
and `uv run ruff check && uv run mypy && uv run pytest` is green. Report what you
built, any deviations from the plan, and open questions.
```
