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

## CREPE and excerpt workflow

The next WP3 pass adds `CrepeParams` and `CrepeTracker` in `transcribe/crepe.py`,
behind the existing `PitchTracker`/`PitchTrack` interface. `get_tracker`, the pipeline
and CLI accept `crepe`; pYIN remains the default. The `crepe` extra installs the
weights bundled in torchcrepe 0.0.24. Shared dataclass fields remain unchanged.

Unlike torchcrepe's convenience `predict` function, each tracker owns its model
cache. Neural inference is batched, but Viterbi decoding runs across the complete
contour to avoid batch-boundary discontinuities. Conversion uses the network's
fixed 20-cent bins without its random pitch dithering. An RMS gate preserves rests;
raw periodicity is retained as confidence, with its limitations documented.
The model's upper pitch limit is 2006 Hz, below C7. Models and numerical imports
are lazy; default core installs remain free of audio dependencies.

WP10 wiring adds `--start`/`--duration` in seconds. Cropping happens before separation
and tracking. Note timestamps retain their original-file offset, so instructions
for a chorus remain aligned with the source. Extreme, invalid and empty excerpts
fail clearly. Excerpt flags on symbolic input fail instead of being silently ignored.

The WP4 harness supports backend selection, capacity, confidence and hop settings,
and records the full configuration. Real CPU tests cover note pitch, resampling,
silence, batch-size invariance, instance-owned models and the excerpt CLI. A separate
manual CI option runs CREPE tests and evaluation. Reference API:
[torchcrepe](https://github.com/maxrmorrison/torchcrepe).

The [28-case CREPE report](../eval/results/2026-10-11-crepe.md) records note F1 of
0.778–1.000 on the seven backing fixtures, compared with pYIN's 0.000–0.133 baseline.
Twenty clean/vibrato/noise cases retain perfect note F1 and tabs; wide-range Twinkle
with vibrato regresses to 0.897 note F1 and 93.3% tabs. A separate, original D-minor
probe reaches 1.000 on clean/noise and 0.941 on vibrato, but 0.000 with backing.
This mixed result is why CREPE is optional and pYIN remains the default. No thresholds
were changed to improve the new probe after seeing its result.

Core checks, strict typing, lint and formatting pass. Three real CREPE CPU tests
verify the tracker and excerpt CLI; a fourth verifies Demucs followed by CREPE.
Two existing clean-audio CLI cases still pass. An isolated environment without
NumPy/Torch also passes the core suite. Hosted CI and GPU inference remain untested.

## First song-to-practice milestone

WP9 and selected Phase 4 work add `render_practice`/`PracticeOptions` and
`preview_wav`/`PreviewOptions`, wired through WP10's CLI. The guide spells out each
hole, breath direction and bend; preserves gaps; groups short phrases; retains source
timestamps; scales practice durations; and flags uncertain notes for review. Transposed
arrangements explicitly describe their pitch shift. The reference-tone WAV uses the
same arranged pitches and slowed timing, omitting unplayable notes as silence.
Both modules use only the standard library and existing contracts. No dataclass
field changes or audio dependencies are introduced to the arrangement/rendering core.

CLI additions are `--format practice`, `--practice-speed` and `--preview`. Input,
guide and preview paths must be distinct (including existing file aliases), preventing
an export from overwriting the source. WAV allocation has a five-minute default limit;
longer recordings should be practiced as excerpts. This is timed guidance in seconds;
tempo estimation and beat notation remain outside this pass.

The included Ode to Joy guide demonstrates the complete output. Tests cover every
action type, low-confidence review, transposition, gaps, slowed timing, preview pitch
preservation, source-file protection, and guide/WAV generation for all seven fixtures.
The optional-audio boundary remains intact in a fresh core-only environment.

This is a useful point for a first assisted user-song trial: select a short, clear
melody, transcribe it, compare the preview, correct uncertain notes, and export the
guide for the user's actual harp. It does not establish reliable unattended full-mix
transcription. A local/self-service web uploader remains a separate Phase 4 task.

Final local verification for this milestone: 345 core tests pass with extras present;
344 pass with five optional-dependency skips in an isolated environment without
NumPy or Torch. The real CREPE/Demucs checks and clean-audio regressions described
above pass. An additional synthesized backing-recording CLI run exports all 15 Ode
to Joy tab tokens exactly, plus a valid mono practice WAV. Formatting, lint, strict
typing, lockfile checks and source/wheel builds pass. Local soundfile decoding
supports WAV, MP3 and FLAC; formats requiring ffmpeg still need that executable.

## Recorded harmonica practice playback

The Phase 4 playback follow-up uses seven actual harmonica recordings from the
CC0 [basic-harmonica](https://github.com/michael02022/basic-harmonica) sample bank.
The first generated reed preset was rejected in listening feedback; it has been
replaced by recorded samples. `PreviewOptions.voice` and CLI `--preview-voice`
select `harmonica` (default) or the existing `sine` reference tone.

The packaged PCM16 WAVs preserve the author's key regions, tuning corrections and
sustain-loop markers. A standard-library sampler uses windowed-sinc conversion
with an anti-aliasing guard band to reach the requested pitch and sample rate.
Long notes continue their sustain loops; releases stay inside each note, keeping
rests and slowed timing exact. Blow/draw timbre differences and bend gestures
are not modeled. The original public-domain dedication, pinned source revision,
file hashes and conversion details accompany the assets.

The change preserves shared music contracts and optional dependency boundaries.
Playback has no runtime download or numerical-library requirement. Tests verify
the recorded waveform survives playback, held notes sustain, both voices preserve
pitch/transposition and silence, high harmonics are filtered before downsampling,
short-note fades remain bounded, and CLI voice selection is reproducible.

Local verification: 354 core tests, formatting, lint and strict typing pass. The
wheel and source distribution build successfully; all seven WAV hashes and the
CC0 dedication were checked inside the wheel. A direct import from that wheel
renders held and transposed notes with Python's standard library alone. The
confirmed private chorus and spoken-cue exercise were regenerated with the
recorded voice, retaining their 22.8-second and 113.95-second durations.

## Chord support and assisted harmony (2026-10-13)

The user requested a fix for omitted harmonica chords. This authorizes the additive
`ChordEvent`, `ChordScore`, `Voicing` and `ChordArrangement` contracts documented in
ARCHITECTURE.md. Existing monophonic fields and behavior remain compatible. The
pass coordinates WP0/WP1/WP2/WP3/WP5/WP6/WP9/WP10, because the limitation crossed
input, physical assignment, rendering and playback boundaries.

Chord assignment enumerates contiguous groups of 2-4 unbent holes on one breath,
plus existing single-note techniques. Every voicing retains the designated melody
pitch and contains only source-requested pitches. Search prioritizes playable
melody, then technique/motion and harmony coverage. Unplayable accompaniment is
reported explicitly; the tool does not silently fill intervening holes with wrong
notes. Over-notes remain opt-in and are never treated as multi-hole chords.

`--chords` preserves simultaneous JSON/MIDI/MusicXML notes and exports bracketed
tabs, timed multi-hole instructions, structured chord JSON and simultaneous WAVs.
Playback mixes real harmonica samples, balances voice count, limits the whole
export's peak and preserves timing/rests at both speeds. The pure core remains
independent of numerical/audio libraries.

`--harmony-audio` adds persistent lower-pitch candidates around a reviewed melody
using an aligned instrumental stem. It never inserts new events or extends tails.
Mixed-recording harmony still needs review: spectral peaks are not proof of note
identity, and chord detection can confuse overtones, bleed and backing layers.
The user's private riff includes source-reviewed chord selections and two actual
harp options; every retained lead pitch/time and every prior cleaned output is
preserved. Those commercial-source artifacts remain under ignored `eval/local/`.

Validation: 408 core tests and four synthesized harmony/audio-CLI tests pass.
Checks cover reed feasibility across all 12 keys, mixed-breath/hole-gap rejection,
melody retention, explicit omissions, JSON round trips, MIDI/MusicXML chord
preservation, source-file protection, simultaneous frequencies, bounded amplitude,
slowed pitch and silent rests. Strict mypy passes for 33 source files. Remaining
scope includes reliable unattended polyphonic transcription, tongue-blocked splits,
chord bends, independent legato voices and acoustic interactions between reeds.

## Live practice listener (2026-10-13)

The user requested an A playing guide and a live visual of performed versus target
notes. The accepted private A/G guides are retained, and both existing arrangements
can be loaded together with `harptab listen`. This coordinated Phase 4 feature owns
the listener server, browser assets and tests, with small CLI/CI/documentation
changes. It consumes existing contracts without changing their fields.

The dependency-free Python adapter validates the reviewed arrangement and provides
actual played pitches, omissions, source timestamps and hole/breath instructions.
A fixed-route loopback HTTP server serves only its bundled UI and those sessions.
The browser captures microphone audio locally, estimates pitches independently of
the target, and displays expected/heard notes, tuning cents and a live pitch trail.
Controls include A/G selection through the supplied files, 50/75/100% speed,
wait-for-match or timed practice, rests, looping, manual steps and guide download.

The 8192-sample spectral detector suppresses high harmonica overtones, rejects
quiet/noisy frames and marks clipping. All chord targets must match within the
selected tolerance. Wait mode needs a stable match and a quiet break between
steps; timed mode uses a three-second count-in and source-relative timing.
Permission denial, pending-request cancellation, stop, device loss and hiding the
tab release microphone resources. No recorded audio leaves the browser.

Validation: 418 Python tests and 15 Node listener tests pass. Signal tests cover
49 pitches across three sample rates, chords/double stops, detuning, wrong octaves,
noise, clipping and all seven packaged CC0 harmonica roots. A private playback
check matched all 55 analyzed windows across the five A/G single-note and chord
voicings used in the current exercise. UI-controller tests use browser API doubles
to check controls, microphone cleanup and recovery. No browser automation surface
was available for rendered visual QA; physical microphone/room accuracy remains
unverified. Chords with octave reeds, missing fundamentals, uneven volume, backing
tracks or reverberation remain challenging and are labeled estimates in the UI.

### Live note display follow-up

The first microphone trial revealed a note flashing for one frame and disappearing.
The UI previously replaced its note/cents readout with a dash on every missing
40 ms frame. `PitchDisplay` now smooths cents across three same-note frames and
keeps the last detection visible for one second, explicitly labeled Last heard.
Actual raw detections still drive practice scoring and the pitch trail; stale notes
cannot earn a match or fill rests. The chart retains past detected pitches in its
vertical range so a dropout no longer hides a pitch outside the target register.

The default noise gate is reduced from -42 dB to -50 dB for quieter sustained input.
A visible level/status readout distinguishes quiet input, unclear/noisy pitch and
clipping. Capture Stop clears the held display. All 19 listener tests pass,
including a microphone-API regression with a one-frame note followed by empty
frames, live display before practice starts, no stale scoring, quiet-note detection,
display expiry, chord/note changes and pitch-trail persistence. Shared music and
scoring contracts are unchanged. Real microphone detection still needs checking
against the user's input after refreshing the page.

### Extra-note detection follow-up

The next user trial reported extra notes. Synthesized harmonic-rich vibrato
reproduced duplicate note names and false upper notes when partials moved outside
the original 32-cent harmonic tolerance. A background tone at one tenth of the
main reed's amplitude also appeared as a second note.

The detector now consolidates peaks for the same note before harmonic rejection,
preserves the strongest peak's unsnapped cents, and tolerates 60 cents of harmonic
spread. After harmonic removal, an independent voice must reach 18% of the
strongest remaining fundamental's amplitude. This relative voice floor removes
faint background notes while retaining quiet standalone playing. No arrangement
pitches are used by these filters, and audible incorrect extra notes still fail
the match. Very uneven chords can lose their faintest reed; that remains a limit.

All 22 listener tests pass, including 168 vibrato combinations across pitches,
sample rates, depths and phases; faint interference; quieter standalone notes;
uneven chords; and visible audible wrong notes. All 55 analyzed windows of the
recorded A/G single notes and chord voicings still match. The live server serves
the updated detector on refresh. Shared music/scoring contracts are unchanged;
microphone accuracy for the user's particular room still requires their trial.

### Specific Ab4 report and diagnostic readout

The user still reported Ab4. The A-harp reed model identifies MIDI 68 (Ab4/G#4)
as hole 3 draw, so removing that pitch from detection would hide a possible real
neighbouring reed. Without the user's signal there is insufficient evidence to
decide whether this is bleed, background sound or a false peak.

The listener now displays Hz, relative amplitude and possible fingerings generated
by `HarmonicaModel`, and can explicitly export six seconds of live note measurements
as a local JSON download. It does not record or upload audio. This gives the next
diagnostic pass actual microphone evidence rather than another speculative filter.
Tests verify A-harp Ab4/F#5 fingerings, genuine Ab4 alone/with the draw chord,
visible measured Hz, and measurements-only export. All 24 listener tests pass.
Shared music/scoring contracts remain unchanged. The specific user-reported Ab4
cause remains unconfirmed until a trial or diagnostic sample is available.

### Start practice flow

The user reported that Start practice was not useful. The previous default waited
indefinitely for a strict chord match, and manual Next reset the session and stopped
it. Start practice now acquires the microphone and begins a visible three-second
count-in in one click. Follow along is the default: the source timing continues
through missed or extra notes while only correct matches receive credit. Step by
step remains available for untimed practice.

The transport sits above the note comparison. A forward-looking pitch timeline,
moving position line, upcoming tab, phrase progress and Play/Rest/Release cues make
the next action visible. Manual skips and step selection preserve running state
and earned matches. Restart clears progress and counts in again when running;
looping repeats with a count-in. Microphone denial and cancellation leave the
practice clock stopped. These changes are confined to listener assets, tests and
documentation; shared music contracts and the pitch detector are unchanged.

Validation: all 30 Node listener tests and 418 Python tests pass (64 audio tests
deselected). Formatting, lint, type checking and wheel/source builds pass. The
running loopback server serves the updated UI, engine and A/G sessions with no-store
headers. Tests cover one-click acquisition, visible count-in/rests, extra-Ab4 input
without stalled timing or false match credit, running skips, pause/resume, restart,
looping and canceled/denied acquisition. UI tests use browser API doubles; an actual
browser surface and the user's physical microphone were unavailable for this pass.

### Practice results and arrangement-driven hole lights

The user requested a way to assess each run and a harmonica with light-up holes,
then clarified that the instrumental is the first of multiple songs to practice.
The listener consumes each loaded arrangement's actions and source name. No song
sequence is embedded in the application. The private instrumental remains the
first loaded exercise, with its existing A and G voicings unchanged.

`load_session` now includes hole, technique, bend depth and pitch for each chosen
action and derives a display title from the source basename. The browser renders
ten holes, lights simultaneous chord holes, labels breath direction and advanced
techniques, and clears the lights during rests, release and completion. Selecting
another arrangement updates the title, notes and diagram together.

`PracticeEngine.report()` supplies live and completed matched/missed/skipped
counts, a percentage of playable steps with sustained matches, and per-step
observations. Unavailable notes are excluded, skips earn no credit, and long gaps
between observations cannot prove a sustained match. The completed report explains
brief matches, tuning, extra/missing notes, quiet/unclear input and clipping. It
remains visible across replay/loop, labels simulated results, and offers step retry
controls. Changing songs clears the previous report. Rhythm and tone grading are
explicitly outside this pitch-match score.

Validation: 35 Node tests and 430 Python tests pass (64 audio tests deselected).
Coverage includes every technique in all 12 harp keys, transposed exercises,
multi-hole lights, song switching, score exclusions, per-step reasons and result
retention. Format, lint, type-check and wheel/source builds pass. The running local
server was restarted and its actual A/G session payloads and new UI assets verified.
Browser-controller tests use API doubles; physical microphone accuracy and rendered
browser appearance remain unverified. Changes stay within the listener work package
and coordinated documentation; shared music contracts are unchanged.

### Recorded take review (2026-10-14)

The user clarified that scores alone were insufficient: they need to review what
they actually played. Practice now records actual microphone audio locally and
retains the full raw detected-note timeline, independently of the live six-second
trail. `TakeRecorder` owns each take's final audio chunks, metadata and observations;
`TakeReview` provides replay, scrubbing, target/heard readouts, step jumps, audio and
notes downloads, selection of earlier takes and explicit deletion. Loops keep
separate takes. Pause, early finish, restart, configuration changes and input loss
save partial takes. Song changes retain the take library. Starting only the mic
and running the simulated demo do not record audio.

Completed audio is decoded locally to seekable PCM WAV where supported, preserving
recorded samples; failures retain the browser's original format with a notice.
Playback stops microphone capture to prevent scoring the replay. Takes persist in
the current tab only, with download as the explicit way to retain them after reload.
The UI and docs now describe recording accurately. Earlier audio was never captured
and cannot be reconstructed. The loopback server remains read-only; its asset list
adds the two JS modules, and CSP permits local Blob audio playback.

Validation: all 43 Node tests and 430 Python tests pass (64 audio tests deselected).
Tests cover final audio chunks, independent loop callbacks, full-history retention,
recording failures, playback stopping capture, seeking actual versus expected notes,
downloads, cross-song retention, partial takes and WAV sample/header correctness.
Format, lint and type checks pass; wheel/source builds and the running server's new
routes, media policy and private A/G session payloads were verified. Native browser
automation returned a missing native-pipe error and the browser inventory was empty,
so physical microphone recording/playback and visual browser QA remain unverified.
No shared music-contract changes were needed; recording is an explicit expansion
of the listener behavior requested by the user.
