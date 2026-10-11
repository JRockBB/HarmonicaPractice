# Synthetic transcription baseline

Date: 2026-10-11
Python: 3.12.10 on Windows

- harptab: 0.1.0
- librosa: 0.11.0
- numpy: 2.5.4
- mir-eval: 0.8.2

All signals are synthesized from hand-entered public-domain excerpts.
No source separation is applied. Backing is a stress test, not a supported mix benchmark.
Note F1 uses exact MIDI pitch and 50 ms onset tolerance; offset F1 also checks offsets.
RPA uses a 50-cent tolerance across reference-voiced frames, including boundaries.
Tab accuracy includes insertions/deletions and uses the fixture's stated harp.

| Fixture | Variant | Note F1 | Offset F1 | RPA | Tab accuracy | Core tab | Seconds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ode_to_joy | clean | 1.000 | 1.000 | 1.000 | 100.0% | 100% | 25.41 |
| ode_to_joy | vibrato | 1.000 | 1.000 | 1.000 | 100.0% | 100% | 20.20 |

## Parameters

```json
{
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

Source separation and ML pitch backends remain unimplemented.
These synthetic results do not establish accuracy on singing or commercial mixes.
