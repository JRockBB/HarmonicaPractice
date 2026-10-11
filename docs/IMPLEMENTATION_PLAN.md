# Implementation review and plan

The initial repository contains five design documents and no source code, package
configuration, tests, or commits. The design specifies Python 3.11+ and the package
name `harptab`; the surrounding Julia development directory does not change that.

## Review findings and implementation decisions

1. **Keep transcription separate.** Build the deterministic arrangement path first
   so transcription errors can later be measured independently from arrangement errors.
2. **Preserve the contracts.** Implement the documented dataclass fields exactly.
   Serialization is additive. Validation belongs in a separate boundary module.
3. **Octaves need explicit semantics.** `Arrangement` has no octave field. Its
   `transpose` records the complete semitone shift, including octaves. Play-along
   uses exactly zero shift. Practice enumerates -6..+5 plus whole octaves that
   overlap the instrument range, including partial fits for wide melodies.
4. **Define over-note policy.** The reference lists a supported subset of over-note
   holes; the gap rule alone cannot select that subset. Store supported holes in
   tuning metadata and derive their pitches from the reeds. Assignment and search
   disable over-notes by default; the physical model exposes all supported actions.
5. **Rank real paths.** Run Viterbi for each search candidate and rank its actual
   cost, avoiding disagreement between the recommendation and final assignment.
   Position and transposition preferences break cost ties. Cost tuning remains empirical.
6. **Key estimates label positions.** Honor provided key metadata. Otherwise use a
   small duration/scale-coverage heuristic with low confidence. It does not control
   pitch feasibility. Short phrases and modal music can have ambiguous keys.
7. **Make fixtures reproducible.** Hand-enter public-domain melody excerpts and
   expected tabs for an explicitly specified harp. Verify global search separately;
   a familiar tune does not uniquely determine an objectively best harp.
8. **MIDI requires a global clock.** Read tempo events across tracks, pair notes by
   track/channel/pitch, exclude percussion, and skyline the selected melodic track.
   Reject type-2 and SMPTE files with an actionable error.

## Delivery sequence

| Step | Work packages | Acceptance |
| --- | --- | --- |
| 1. Package foundation | WP0 | Frozen contracts, JSON round trips, uv lockfile, CI |
| 2. Pure arrangement | WP1, WP5, WP6 | Exact instrument tables, all positions, globally optimal assignment tests, pitch-preserving search |
| 3. Symbolic release | WP2, WP9, symbolic WP10 | JSON/MIDI CLI, optional MusicXML, exact fixture tabs, tempo-map and overlap tests |
| 4. Measurable transcription | WP3, WP4, WP7 | Synthesized clean/noisy/vibrato audio, pYIN pitch and note F-measure targets, dated baseline |
| 5. Full-song audio | WP8, remaining WP10, WP11 | Cached Demucs stems, measured CPU runtime and improvement over no separation, CLI integration |
| 6. Usability | Selected Phase 4 items | Rhythm display, editable transcription workflow, playback |

The first implementation pass covered steps 1–3. The following audio pass implements
step 4 and wires the clean-audio path into the CLI. Those passes were committed as
`9434bb0` at the user's request. Step 5 continues on `feature/demucs-separation`, with
WP8 followed by its WP10 wiring and WP4/WP11 evaluation/documentation in the same tree.
Beat tracking retains an explicit unimplemented interface.

## Deliberate adjustments to the original roadmap

- The symbolic CLI lands before all audio work, making M1 usable immediately.
- Pure-core import enforcement includes transitive package imports.
- The `audio` extra contains librosa and soundfile; `evaluation` adds mir_eval.
  The separate `separation` extra adds Demucs and Torch. Torchcrepe and basic-pitch
  remain deferred until their adapters and compatibility checks exist.
- CI covers core tests and wheel building. The audio test/evaluation job is separate
  and runs on manual workflow dispatch.
- No dataclass field changes are required. Future tuning metadata, segmentation
  diagnostics, and schema versioning should be decided before adding them to contracts.

## Known limits to address next

Key estimation is heuristic; MIDI pedal/expression and tempo-aware rhythm notation
are not modeled. MusicXML repeat expansion is not automatic. Custom tunings can be
supplied through a `Tuning` object, but named alternate tunings are not yet provided.
No commercial recording or copied website tab belongs in the repository.

Dependency reference: [Mido MIDI file API](https://mido.readthedocs.io/en/latest/api.html).

## Verification for the first symbolic pass

Locally verified on Windows with Python 3.12.10:

- 251 tests passed with the optional MusicXML dependency installed.
- Ruff formatting and lint checks passed.
- Strict mypy checks passed for all 25 source modules.
- The uv lockfile resolves consistently; wheel and source-distribution builds passed.
- The documented CLI example and fixture-to-MIDI generator ran successfully.

CI is configured for core checks on Windows/Linux with Python 3.11, 3.12 and 3.13,
plus a separate MusicXML job. Hosted CI has not run from this local working tree.
This first pass did not validate audio accuracy or separation runtime.

## Audio implementation decisions

- Preserve `PitchTrack` and all shared dataclass fields. Audio dependencies are
  imported inside loading/tracking functions; contour segmentation uses the standard library.
- Decode through soundfile, resample through librosa, and use an explicit ffmpeg
  subprocess fallback for unsupported codecs. Librosa's audioread fallback is deprecated.
- Use centered pYIN timestamps plus a short RMS silence gate so repeated notes
  separated by rests remain separate. Infer stable notes using median smoothing,
  sustained pitch changes, brief-dropout bridging and onset-scoop absorption.
- Estimate global sub-semitone tuning with circular residual statistics. Preserve
  the measured deviation in each note's existing `cents_offset` field.
- The initial audio pass required `--no-separate`; WP8 now supplies the default
  separation stage. `transcribe` writes editable Melody JSON;
  ordinary file input runs transcription followed by arrangement.
- Evaluation synthesizes known melodies with 60 ms articulation, additive harmonics,
  deterministic noise, vibrato, or backing. References use the actual sounding
  durations; pYIN receives only the waveform. Scores use mir_eval note matching and
  frame pitch metrics, plus tab edit accuracy against the independently entered tabs.
- Beat snapping, CREPE and basic-pitch remain future work.

An initial tuning comparison on Ode to Joy retained the 128-sample hop and
0.1-semitone pitch grid. Doubling both reduced runtime, but vibrato note F1 fell
from 1.000 to 0.857 and tab accuracy from 100% to 75%. The faster setting was
rejected. Raw measurements are in `eval/results/initial-ode-to-joy.md` and
`eval/results/tuning-ode-to-joy.md`; timings include startup and concurrent work
and are illustrative, not isolated hardware benchmarks.

Reference APIs: [librosa loading](https://librosa.org/doc/0.11.0/generated/librosa.load.html),
[mir_eval note matching](https://github.com/mir-evaluation/mir_eval/blob/main/mir_eval/transcription.py),
[mir_eval melody metrics](https://mir-eval.readthedocs.io/latest/api/melody.html).

## Audio verification and next step

The [dated baseline](../eval/results/2026-10-11.md) covers seven melodies and four
variants (28 cases). All 21 clean, vibrato and noise cases reached note/offset F1
of 1.000 and 100% tab accuracy. Raw pitch accuracy ranged from 0.993 to 1.000.
Backing cases reached only 0.000–0.133 note F1 and 0–7.1% tab accuracy. This is a
synthetic baseline, not evidence of accuracy on real singing or full mixes.

The 30 audio integration tests passed, including all clean/vibrato fixtures,
the 95% voiced-frame pitch criterion, decoder failures and the audio CLI workflow.
The separate metric-calculation test also passed. A fresh installation without
extras passed its core suite (269 tests at that check, plus the subsequently added
recording-end clipping test). Lint, formatting, strict typing, lockfile validation,
and source/wheel builds passed. Hosted CI remains unexecuted locally.

## Source-separation implementation decisions

- Use the maintained [demucs-infer](https://github.com/openmirlab/demucs-infer)
  inference fork. Original Demucs 4.0.1 pins TorchAudio below 2.1; that dependency
  set does not fit the current Python 3.12 environment. The fork retains official
  Demucs architectures/checkpoints and supports modern PyTorch loading.
- Keep numerical/model imports lazy. The arranger, CLI import and cache-hit path
  do not load Torch. Core installs continue to support all symbolic operations.
- `separate` accepts mono input and returns finite float32 at the same rate and exact
  sample count. Duplicate mono to stereo for Demucs, then average and resample its
  output back to the requested rate. Preserving original stereo for separation would
  require revisiting the stage-1 mono contract and is deferred.
- `SeparationParams` controls model, device, chunk length, overlap, shift averaging,
  cache root and stem caching. Defaults disable random shifts. CPU works; automatic
  CUDA selection is implemented but GPU inference remains untested locally.
- Cache keys include the source-file digest, decoded samples, sample rate, model,
  stem, inference settings and relevant package versions. Read with pickle disabled,
  validate key/shape/dtype/finite samples, recover by recomputing corrupt entries,
  and atomically replace completed cache files. Downloaded weights and stems live
  outside source control. `--no-cache` bypasses stems but retains model downloads.
- Wire `--stem`, `--device`, `--separation-model`, `--cache-dir`, `--no-cache` and the
  existing `--no-separate` through the CLI. Progress stays on stderr; editable
  Melody JSON and all shared dataclasses retain their existing contracts.
- Extend WP4 through `python -m eval.separation`, comparing the same backing fixtures
  before and after separation. The synthetic instrumental lead uses `other`;
  Demucs source categories cannot isolate a melody from other instruments in that stem.
- Gate real model-download tests behind `HARPTAB_TEST_DEMUCS=1`, with a separate
  manual CI option. Ordinary core/audio tests exercise configuration, caching,
  corrupt-cache recovery, dependency errors, pipeline wiring and bypass without downloads.

Next work should be selected from the measured separation report: improve melody
tracking under residual accompaniment before claiming full-mix transcription quality.
Keep CREPE/basic-pitch optional and validate their dependency compatibility first.
No shared dataclass changes are required by this pass.

## Separation accuracy and next iteration

The [backing comparison](../eval/results/2026-10-11-separation.md) uses the same seven
fixtures and defaults as the baseline. Mean frame pitch accuracy changes from about
30.5% to 32.1%. Mary improves from 22.7% to 68.9%; Twinkle and its wide-range variant
regress. Wide-range Twinkle's note F1 improves from 0.133 to 0.353 and tab accuracy
from 7.1% to 21.4%. The other six fixtures still produce zero note F1.

This supports only a modest average pitch improvement. A functioning separator does
not establish a reliable mixed-recording-to-tab pipeline. The next accuracy iteration
should inspect octave errors and missing voiced spans on these saved references,
then compare an optional CREPE tracker through the existing `PitchTrack` boundary.
Keep pYIN as the default until a candidate improves the backing cases without
regressing clean, vibrato and noise fixtures. Add held-out synthesized mixtures to
avoid selecting settings solely for these seven short excerpts.

## Source-separation verification

On Windows/Python 3.12.10, a 180-second synthesized WAV separated in 221.03 seconds
using an AMD Ryzen 7 5800H CPU and `OMP_NUM_THREADS=4`. A cached read took 0.062
seconds. Output sample count, dtype, finite values and repeatability were checked;
timings exclude pitch tracking, decoding and initial model download.

- 292 core tests pass with optional dependencies present.
- 23 cache/validation audio tests pass without loading a model.
- Two real Demucs integration tests pass, including frequency/rate preservation,
  cache reuse, and the CLI's clean JSON stdout.
- Two clean-audio CLI regression cases pass (Ode to Joy and silence).
- An isolated environment verified that NumPy and Torch were absent, then passed
  289 tests with five optional-dependency skips. The two later missing-extra-message
  tests also pass in the normal suite with dependencies explicitly mocked absent.
- Ruff formatting/lint, strict mypy, lockfile validation, workflow YAML parsing and
  source/wheel builds pass. Hosted CI and CUDA inference have not been run locally.

WP8's CPU and caching requirements are met; average pitch accuracy improves only
slightly. The remaining full-mix quality limitations are explicit above. This pass
requires no shared-contract changes and coordinates only WP8, its WP10 wiring,
and WP4/WP11 verification and documentation.
