# Source separation: synthesized backing comparison

Date: 2026-10-11; Python 3.12.10 on Windows.
Processor: AMD64 Family 25 Model 80 Stepping 0, AuthenticAMD; logical CPUs: 16.
CPU model confirmed through Windows CIM: AMD Ryzen 7 5800H, 8 physical cores.
OMP_NUM_THREADS: 4.

CPU inference; stem caching disabled for accuracy timings. Model weights may be cached.
Additive leads use the `other` stem by default; these are not vocal recordings.
Pitch and note metrics have the same definitions as the original baseline.
All audio is synthesized from hand-entered public-domain melodies.

- demucs-infer: 4.3.0
- torch: 2.14.1
- librosa: 0.11.0
- numpy: 2.5.4
- mir-eval: 0.8.2

| Fixture | Note F1 before | Note F1 after | RPA before | RPA after | Tab before | Tab after | Separation seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| amazing_grace_low | 0.000 | 0.000 | 0.000 | 0.000 | 0.0% | 0.0% | 21.80 |
| greensleeves | 0.000 | 0.000 | 0.099 | 0.099 | 0.0% | 0.0% | 8.51 |
| mary | 0.000 | 0.000 | 0.227 | 0.689 | 0.0% | 0.0% | 17.73 |
| mary_cross_harp | 0.000 | 0.000 | 0.000 | 0.000 | 0.0% | 0.0% | 20.14 |
| ode_to_joy | 0.000 | 0.000 | 0.465 | 0.465 | 0.0% | 0.0% | 19.10 |
| twinkle | 0.000 | 0.000 | 0.636 | 0.353 | 0.0% | 0.0% | 18.01 |
| twinkle_wide | 0.133 | 0.353 | 0.708 | 0.638 | 7.1% | 21.4% | 21.03 |

Mean RPA rises from approximately 0.305 to 0.321. Mary improves, four fixtures are
unchanged, and two regress. Only wide-range Twinkle gains note/tab accuracy; six
fixtures still have zero note F1. Full-mix transcription remains experimental.
Short-fixture timings include first-use overhead and concurrent development checks;
the three-minute CPU measurement below ran after those checks finished.

## CPU file and cache timing

- WAV duration: 180 seconds at 22050 Hz, mono float32.
- Uncached separation: 221.03 seconds (1.23x audio duration).
- Cached read: 0.062 seconds; output matched within float32 tolerance.
- Timings exclude WAV decoding/file hashing and include model initialization; weights were already downloaded.
- Exact sample count, finite float32 output, and cache-hit progress were asserted.

Reproduce with `OMP_NUM_THREADS=4` in the environment and:

```sh
uv run --extra separation --extra evaluation python -m eval.separation --benchmark-seconds 180
```

The benchmark measures inference without stem caching, then separately populates
the cache and times a read. This first run performed two full inferences to verify
repeatability. It times separation only, not end-to-end pitch tracking.

## Parameters

```json
{
  "separation": {
    "model": "htdemucs",
    "device": "cpu",
    "shifts": 0,
    "overlap": 0.25,
    "segment": 7.0,
    "cache_dir": ".tools\\separation-cache",
    "use_cache": false
  },
  "stem": "other",
  "pitch": {
    "sample_rate": 22050,
    "fmin": 65.406391,
    "fmax": 2093.004522,
    "frame_length": 1024,
    "hop_length": 128,
    "resolution": 0.1,
    "silence_rms": 0.0001,
    "relative_silence": 0.03
  },
  "segment": {
    "min_duration": 0.08,
    "min_confidence": 0.5,
    "pitch_jump": 0.7,
    "change_hold": 0.045,
    "median_frames": 5,
    "history": 0.2,
    "bridge_gap": 0.012,
    "onset_scoop": 0.1,
    "correct_tuning": true
  },
  "synth": {
    "sample_rate": 22050,
    "amplitude": 0.35,
    "articulation": 0.06,
    "fade": 0.008,
    "tail": 0.1,
    "vibrato_cents": 45.0,
    "vibrato_hz": 5.5,
    "noise_amplitude": 0.012,
    "backing_amplitude": 0.06,
    "drum_amplitude": 0.06,
    "detune_cents": 0.0,
    "seed": 1729
  }
}
```

Demucs separates source categories, not individual melodies sharing the `other` stem.
These fixtures do not establish performance on vocals or real-world mixes.
