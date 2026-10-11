"""Run with ``uv run --extra evaluation python -m eval`` from the repository root."""

import argparse
import json
import platform
import sys
from dataclasses import asdict
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import perf_counter

from harptab.core.assign import assign
from harptab.core.instrument import HarmonicaModel
from harptab.models import Melody
from harptab.render.text import action_token
from harptab.transcribe.crepe import CrepeParams
from harptab.transcribe.pitch import PyinParams, get_tracker
from harptab.transcribe.segment import SegmentParams, segment


def main() -> int:
    """Record reproducible synthetic metrics, or N/A for unavailable audio dependencies."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--variant",
        nargs="+",
        choices=("clean", "vibrato", "noise", "backing"),
        default=["clean", "vibrato", "noise", "backing"],
    )
    parser.add_argument("--fixture", help="evaluate only the named fixture")
    parser.add_argument("--pitch-backend", choices=("pyin", "crepe"), default="pyin")
    parser.add_argument("--crepe-model", choices=("full", "tiny"), default="full")
    parser.add_argument("--hop-length", type=int)
    parser.add_argument("--resolution", type=float, default=PyinParams().resolution)
    parser.add_argument("--min-confidence", type=float, default=SegmentParams().min_confidence)
    args = parser.parse_args()
    available = True
    try:
        from eval.metrics import score, token_accuracy
        from eval.synth import SynthParams, synthesize

        if args.pitch_backend == "crepe":
            version("torchcrepe")
    except (ImportError, PackageNotFoundError):
        available = False
    params: PyinParams | CrepeParams
    if args.pitch_backend == "crepe":
        params = CrepeParams(
            hop_length=args.hop_length or CrepeParams().hop_length, model=args.crepe_model
        )
    else:
        params = PyinParams(
            hop_length=args.hop_length or PyinParams().hop_length, resolution=args.resolution
        )
    tracker = get_tracker(args.pitch_backend, params)
    settings = SegmentParams(min_confidence=args.min_confidence)
    synth_params = SynthParams(sample_rate=params.sample_rate) if available else None
    output = args.output or Path("eval/results") / f"{date.today()}-{args.pitch_backend}.md"
    lines = [
        "# Synthetic transcription baseline",
        "",
        f"Date: {date.today()}",
        f"Python: {platform.python_version()} on {platform.system()}",
        f"Pitch backend: {args.pitch_backend}",
        "",
    ]
    for name in ("harptab", "librosa", "numpy", "mir-eval", "torchcrepe"):
        try:
            lines.append(f"- {name}: {version(name)}")
        except PackageNotFoundError:
            lines.append(f"- {name}: unavailable")
    lines += [
        "",
        "All signals are synthesized from hand-entered public-domain excerpts.",
        "No source separation is applied. Backing is a stress test, not a supported mix benchmark.",
        "Note F1 uses exact MIDI pitch and 50 ms onset tolerance; offset F1 also checks offsets.",
        "RPA uses a 50-cent tolerance across reference-voiced frames, including boundaries.",
        "Tab accuracy includes insertions/deletions and uses the fixture's stated harp.",
        "Times include tracking and segmentation; startup and concurrent work affect wall time.",
        "",
        "| Fixture | Variant | Note F1 | Offset F1 | RPA | Tab accuracy | Core tab | Seconds |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    fixtures = Path(__file__).resolve().parents[1] / "tests/fixtures/melodies"
    fixture_paths = sorted(fixtures.glob("*.melody.json"))
    if args.fixture and not any(
        path.name == args.fixture + ".melody.json" for path in fixture_paths
    ):
        parser.error(f"unknown fixture: {args.fixture}")
    for path in fixture_paths:
        name = path.name.removesuffix(".melody.json")
        if args.fixture and args.fixture != name:
            continue
        melody = Melody.from_dict(json.loads(path.read_text(encoding="utf-8")))
        expected_path = path.with_name(name + ".expected.txt")
        header, tokens = expected_path.read_text().strip().split("\n", 1)
        key = int(header.removeprefix("# harp_key, position: ").split(",")[0])
        harp = HarmonicaModel(key)
        core_tokens = [action_token(a) for a in assign(melody, harp).actions]
        core = "100%" if core_tokens == tokens.split() else "MISMATCH"
        for variant in args.variant:
            if available:
                print(f"Evaluating {name}: {variant}", file=sys.stderr, flush=True)
                signal, reference = synthesize(melody, variant, synth_params)
                begin = perf_counter()
                track = tracker.track(signal, params.sample_rate)
                estimated = Melody(segment(track, settings))
                elapsed = perf_counter() - begin
                metrics = score(reference, estimated, track)
                actual = [action_token(a) for a in assign(estimated, harp).actions]
                tab = token_accuracy(tokens.split(), actual)
                values = (
                    f"{metrics.onset_f1:.3f} | {metrics.offset_f1:.3f} | "
                    f"{metrics.raw_pitch_accuracy:.3f} | {tab:.1%} | {core} | {elapsed:.2f}"
                )
            else:
                values = f"N/A | N/A | N/A | N/A | {core} | N/A"
            lines.append(f"| {name} | {variant} | {values} |")
    lines += [
        "",
        "## Parameters",
        "",
        "```json",
        json.dumps(
            {
                "pitch": asdict(params),
                "segment": asdict(settings),
                "synth": asdict(synth_params) if synth_params is not None else None,
            },
            indent=2,
        ),
        "```",
        "",
        "For a source-separation comparison, run `python -m eval.separation` with its extras.",
        "CREPE confidence is model periodicity; it is not calibrated to pYIN probabilities.",
        "These synthetic results do not establish accuracy on singing or commercial mixes.",
    ]
    if not available:
        lines += [
            "",
            "Install dependencies with `uv sync --extra evaluation`; add `--extra crepe` "
            "for the CREPE backend.",
        ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
