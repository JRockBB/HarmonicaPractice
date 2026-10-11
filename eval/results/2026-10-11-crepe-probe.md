# CREPE: original melody probe

Date: 2026-10-11

An original D-minor note sequence with register jumps, uneven durations and rests.
Defined after the initial adapter implementation; no settings were tuned to this probe.
No source separation is applied. Audio is synthetic, not a real-singing benchmark.

| Variant | Note F1 | Offset F1 | RPA |
| --- | ---: | ---: | ---: |
| clean | 1.000 | 1.000 | 1.000 |
| vibrato | 0.941 | 0.824 | 1.000 |
| noise | 1.000 | 1.000 | 1.000 |
| backing | 0.000 | 0.000 | 0.000 |

## Reproduction

Run `uv run --extra crepe --extra evaluation python -m eval.crepe_probe`.

```json
{
  "melody": {
    "notes": [
      {
        "pitch": 62,
        "start": 0.13,
        "duration": 0.31,
        "confidence": 1.0,
        "cents_offset": 0.0
      },
      {
        "pitch": 69,
        "start": 0.53,
        "duration": 0.43,
        "confidence": 1.0,
        "cents_offset": 0.0
      },
      {
        "pitch": 65,
        "start": 1.05,
        "duration": 0.27,
        "confidence": 1.0,
        "cents_offset": 0.0
      },
      {
        "pitch": 74,
        "start": 1.4100000000000001,
        "duration": 0.6,
        "confidence": 1.0,
        "cents_offset": 0.0
      },
      {
        "pitch": 67,
        "start": 2.1,
        "duration": 0.39,
        "confidence": 1.0,
        "cents_offset": 0.0
      },
      {
        "pitch": 72,
        "start": 2.58,
        "duration": 0.47,
        "confidence": 1.0,
        "cents_offset": 0.0
      },
      {
        "pitch": 60,
        "start": 3.14,
        "duration": 0.36,
        "confidence": 1.0,
        "cents_offset": 0.0
      },
      {
        "pitch": 64,
        "start": 3.59,
        "duration": 0.52,
        "confidence": 1.0,
        "cents_offset": 0.0
      }
    ],
    "tempo_bpm": 110,
    "beats": null,
    "key_estimate": {
      "tonic": 2,
      "mode": "minor",
      "confidence": 1
    },
    "source": ""
  },
  "pitch": {
    "sample_rate": 16000,
    "hop_length": 160,
    "fmin": 65.406391,
    "fmax": 2000.0,
    "model": "full",
    "device": "cpu",
    "batch_size": 128,
    "transition_width": 12,
    "min_periodicity": 0.21,
    "median_frames": 3,
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
    "sample_rate": 16000,
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
    "seed": 2903
  }
}
```
