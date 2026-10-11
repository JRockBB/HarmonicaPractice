"""A fresh, original melody probe, separate from the seven tuning fixtures."""

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from eval.metrics import score
from eval.synth import SynthParams, synthesize
from harptab.models import KeyEstimate, Melody, NoteEvent
from harptab.transcribe.crepe import CrepeParams, CrepeTracker
from harptab.transcribe.segment import SegmentParams, segment


def main() -> None:
    """Record four synthetic variants without changing tracker or segmentation defaults."""
    pitches = [62, 69, 65, 74, 67, 72, 60, 64]
    durations = [0.31, 0.43, 0.27, 0.60, 0.39, 0.47, 0.36, 0.52]
    start = 0.13
    notes = []
    for pitch, duration in zip(pitches, durations, strict=True):
        notes.append(NoteEvent(pitch, start, duration))
        start += duration + 0.09
    melody = Melody(notes, key_estimate=KeyEstimate(2, "minor", 1), tempo_bpm=110)
    params = CrepeParams(device="cpu")
    synth_params = SynthParams(sample_rate=params.sample_rate, seed=2903)
    tracker = CrepeTracker(params)
    lines = [
        "# CREPE: original melody probe",
        "",
        f"Date: {date.today()}",
        "",
        "An original D-minor note sequence with register jumps, uneven durations and rests.",
        "Defined after the initial adapter implementation; no settings were tuned to this probe.",
        "No source separation is applied. Audio is synthetic, not a real-singing benchmark.",
        "",
        "| Variant | Note F1 | Offset F1 | RPA |",
        "| --- | ---: | ---: | ---: |",
    ]
    for variant in ("clean", "vibrato", "noise", "backing"):
        print(f"Probe: {variant}", flush=True)
        audio, reference = synthesize(melody, variant, synth_params)
        track = tracker.track(audio, params.sample_rate)
        metrics = score(reference, Melody(segment(track)), track)
        lines.append(
            f"| {variant} | {metrics.onset_f1:.3f} | {metrics.offset_f1:.3f} | "
            f"{metrics.raw_pitch_accuracy:.3f} |"
        )
        print(lines[-1], flush=True)
    lines += [
        "",
        "## Reproduction",
        "",
        "Run `uv run --extra crepe --extra evaluation python -m eval.crepe_probe`.",
        "",
        "```json",
        json.dumps(
            {
                "melody": melody.to_dict(),
                "pitch": asdict(params),
                "segment": asdict(SegmentParams()),
                "synth": asdict(synth_params),
            },
            indent=2,
        ),
        "```",
        "",
    ]
    path = Path(f"eval/results/{date.today()}-crepe-probe.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(path)


if __name__ == "__main__":
    main()
