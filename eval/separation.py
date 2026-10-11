"""Compare backed fixtures before/after Demucs; optionally time a synthesized CPU file."""

import argparse
import json
import os
import platform
from dataclasses import asdict
from datetime import date
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

import numpy as np
import soundfile as sf

from eval.metrics import score, token_accuracy
from eval.synth import SynthParams, synthesize
from harptab.core.assign import assign
from harptab.core.instrument import HarmonicaModel
from harptab.models import Melody
from harptab.render.text import action_token
from harptab.transcribe.load import load_audio
from harptab.transcribe.pitch import PyinParams, PyinTracker
from harptab.transcribe.segment import SegmentParams, segment
from harptab.transcribe.separate import MODELS, STEMS, SeparationParams, file_digest, separate


def main() -> int:
    """Write a measured comparison without asserting that separation improves every mix."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(f"eval/results/{date.today()}-separation.md")
    )
    parser.add_argument("--cache-dir", type=Path, default=Path(".tools/separation-cache"))
    parser.add_argument("--stem", choices=STEMS, default="other")
    parser.add_argument("--model", choices=MODELS, default="htdemucs")
    parser.add_argument("--fixture", help="evaluate only the named fixture")
    parser.add_argument(
        "--benchmark-seconds", type=int, default=0, help="also time a CPU WAV of this length"
    )
    args = parser.parse_args()
    if args.benchmark_seconds < 0:
        parser.error("--benchmark-seconds must be nonnegative")
    params = SeparationParams(
        model=args.model, device="cpu", cache_dir=args.cache_dir, use_cache=False
    )
    pitch = PyinParams()
    tracker = PyinTracker(pitch)
    lines = [
        "# Source separation: synthesized backing comparison",
        "",
        f"Date: {date.today()}; Python {platform.python_version()} on {platform.system()}.",
        f"Processor: {platform.processor()}; logical CPUs: {os.cpu_count()}.",
        f"OMP_NUM_THREADS: {os.environ.get('OMP_NUM_THREADS', 'unset')}.",
        "",
        "CPU inference; stem caching disabled for accuracy timings. Model weights may be cached.",
        "Additive leads use the `other` stem by default; these are not vocal recordings.",
        "Pitch and note metrics have the same definitions as the original baseline.",
        "All audio is synthesized from hand-entered public-domain melodies.",
        "",
    ]
    for name in ("demucs-infer", "torch", "librosa", "numpy", "mir-eval"):
        lines.append(f"- {name}: {version(name)}")
    lines += [
        "",
        "| Fixture | Note F1 before | Note F1 after | RPA before | RPA after | "
        "Tab before | Tab after | Separation seconds |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    fixtures = Path(__file__).resolve().parents[1] / "tests/fixtures/melodies"
    paths = sorted(fixtures.glob("*.melody.json"))
    if args.fixture:
        paths = [path for path in paths if path.name == args.fixture + ".melody.json"]
        if not paths:
            parser.error(f"unknown fixture: {args.fixture}")
    for path in paths:
        name = path.name.removesuffix(".melody.json")
        print(f"Evaluating separation: {name}", flush=True)
        melody = Melody.from_dict(json.loads(path.read_text(encoding="utf-8")))
        audio, reference = synthesize(melody, "backing")
        header, tokens = path.with_name(name + ".expected.txt").read_text().strip().split("\n", 1)
        key = int(header.removeprefix("# harp_key, position: ").split(",")[0])
        harp = HarmonicaModel(key)
        begin = perf_counter()
        isolated = separate(audio, pitch.sample_rate, args.stem, params=params, progress=print)
        elapsed = perf_counter() - begin
        results = []
        for waveform in (audio, isolated):
            track = tracker.track(waveform, pitch.sample_rate)
            estimated = Melody(segment(track))
            metrics = score(reference, estimated, track)
            tab = token_accuracy(
                tokens.split(), [action_token(a) for a in assign(estimated, harp).actions]
            )
            results.append((metrics, tab))
        (before, tab_before), (after, tab_after) = results
        lines.append(
            f"| {name} | {before.onset_f1:.3f} | {after.onset_f1:.3f} | "
            f"{before.raw_pitch_accuracy:.3f} | {after.raw_pitch_accuracy:.3f} | "
            f"{tab_before:.1%} | {tab_after:.1%} | {elapsed:.2f} |"
        )
        print(lines[-1], flush=True)
    if args.benchmark_seconds:
        seconds = args.benchmark_seconds
        # Use an actual file and the public decode boundary for the CPU acceptance benchmark.
        args.cache_dir.mkdir(parents=True, exist_ok=True)
        benchmark_path = args.cache_dir / f"synthetic-{seconds}s.wav"
        size = seconds * pitch.sample_rate
        signal = np.tile(audio, (size + len(audio) - 1) // len(audio))[:size]
        sf.write(benchmark_path, signal, pitch.sample_rate, subtype="FLOAT")
        signal = load_audio(benchmark_path, pitch.sample_rate)
        digest = file_digest(benchmark_path)
        cached_params = SeparationParams(model=args.model, device="cpu", cache_dir=args.cache_dir)
        # A benchmark always measures inference, even on a rerun with a populated stem cache.
        print(f"Timing {seconds}s CPU file...", flush=True)
        begin = perf_counter()
        expected = separate(signal, pitch.sample_rate, args.stem, params=params, source_hash=digest)
        cold = perf_counter() - begin
        # Populate through the public cache path, then measure an actual cache hit.
        separate(signal, pitch.sample_rate, args.stem, params=cached_params, source_hash=digest)
        messages: list[str] = []
        begin = perf_counter()
        cached = separate(
            signal,
            pitch.sample_rate,
            args.stem,
            params=cached_params,
            source_hash=digest,
            progress=messages.append,
        )
        warm = perf_counter() - begin
        np.testing.assert_allclose(cached, expected, rtol=1e-5, atol=1e-6)
        assert messages == [f"Using cached {args.stem} stem..."]
        assert cached.shape == (size,) and cached.dtype == np.float32 and np.isfinite(cached).all()
        lines += [
            "",
            "## CPU file and cache timing",
            "",
            f"- WAV duration: {seconds} seconds at {pitch.sample_rate} Hz, mono float32.",
            f"- Uncached separation: {cold:.2f} seconds ({cold / seconds:.2f}x audio duration).",
            f"- Cached read: {warm:.3f} seconds; output matched within float32 tolerance.",
            "- Timings exclude WAV decoding/file hashing and include model initialization; "
            "weights were already downloaded.",
            "- Exact sample count, finite float32 output, and cache-hit progress were asserted.",
        ]
    lines += [
        "",
        "## Parameters",
        "",
        "```json",
        json.dumps(
            {
                "separation": asdict(params),
                "stem": args.stem,
                "pitch": asdict(pitch),
                "segment": asdict(SegmentParams()),
                "synth": asdict(SynthParams()),
            },
            indent=2,
            default=str,
        ),
        "```",
        "",
        "Demucs separates source categories, not individual melodies sharing the `other` stem.",
        "These fixtures do not establish performance on vocals or real-world mixes.",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
