"""Command-line entry point for arrangement and optional audio transcription."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from harptab.core.search import search
from harptab.pipeline import load_melody, transcribe_audio
from harptab.render.json import render_json
from harptab.render.text import render_text


def _harps(value: str) -> list[int]:
    naturals = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    keys = []
    for item in value.split(","):
        name = item.strip().replace("♯", "#").replace("♭", "b")
        if not name or name[0].upper() not in naturals or name[1:] not in ("", "#", "b"):
            raise argparse.ArgumentTypeError(
                f"invalid harp key {item!r}; use names such as C,G,A,Bb"
            )
        accidental = name[1:]
        keys.append(
            (naturals[name[0].upper()] + accidental.count("#") - accidental.count("b")) % 12
        )
    return keys


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``harptab [arrange|transcribe] FILE``; errors return status 2 without a traceback."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="harptab", description="Arrange a melody for harmonica")
    command = "arrange"
    if arguments and arguments[0] in ("arrange", "transcribe"):
        command = arguments.pop(0)
    parser.add_argument("file", type=Path, help="melody JSON, MIDI, MusicXML or audio file")
    parser.add_argument("--harps", type=_harps, help="owned harmonicas, e.g. C,G,A")
    parser.add_argument("--mode", choices=("play_along", "practice"), default="play_along")
    parser.add_argument(
        "--skill", choices=("beginner", "intermediate", "advanced"), default="intermediate"
    )
    parser.add_argument("--overblows", action="store_true", help="allow overblows and overdraws")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--alternatives", type=int, default=0, metavar="N", help="number of additional choices"
    )
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument(
        "--no-separate",
        action="store_true",
        help="transcribe a clean solo source without source separation",
    )
    parser.add_argument("--pitch-backend", default="pyin", choices=("pyin",))
    args = parser.parse_args(arguments)
    if args.alternatives < 0:
        parser.error("--alternatives must be nonnegative")

    def progress(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    try:
        if command == "transcribe":
            melody = transcribe_audio(
                args.file,
                no_separate=args.no_separate,
                pitch_backend=args.pitch_backend,
                progress=progress,
            )
            output = json.dumps(melody.to_dict(), indent=2, allow_nan=False) + "\n"
        else:
            melody = load_melody(
                args.file,
                no_separate=args.no_separate,
                pitch_backend=args.pitch_backend,
                progress=progress,
            )
            choices = search(
                melody,
                mode=args.mode,
                harps=args.harps,
                skill=args.skill,
                top_n=args.alternatives + 1,
                overblows=args.overblows,
            )
            if not choices:
                raise ValueError("input contains no melody notes")
            renderer = render_json if args.format == "json" else render_text
            output = renderer(melody, choices[0], alternatives=choices[1:])
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
    except (OSError, ValueError, ImportError, NotImplementedError, EOFError) as error:
        print(f"harptab: {error}", file=sys.stderr)
        return 2
    return 0
