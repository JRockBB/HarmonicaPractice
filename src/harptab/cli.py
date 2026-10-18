"""Command-line entry point for arrangement and optional audio transcription."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from harptab.core.chords import search_chords
from harptab.core.search import search
from harptab.pipeline import load_melody, load_score, transcribe_audio
from harptab.playback import PREVIEW_VOICES, PreviewOptions, preview_chords_wav, preview_wav
from harptab.render.chords import render_chord_json, render_chord_practice, render_chord_text
from harptab.render.json import render_json
from harptab.render.practice import PracticeOptions, render_practice
from harptab.render.text import render_text
from harptab.transcribe.separate import MODELS, STEMS, SeparationParams


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
    """Run arrangement, transcription or local listening; input errors return status 2."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "listen":
        from harptab.listener import listen_main

        return listen_main(arguments[1:])
    parser = argparse.ArgumentParser(
        prog="harptab",
        description="Arrange a melody for harmonica",
        epilog="Live microphone practice: harptab listen arrangement.json [another.json]",
    )
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
    parser.add_argument(
        "--chords",
        action="store_true",
        help="preserve and arrange simultaneous notes from JSON/MIDI/MusicXML",
    )
    parser.add_argument(
        "--harmony-audio",
        type=Path,
        help="add harmony candidates to reviewed melody JSON using an isolated instrumental stem; "
        "implies --chords and requires matching source timestamps",
    )
    parser.add_argument("--format", choices=("text", "json", "practice"), default="text")
    parser.add_argument(
        "--practice-speed", type=float, default=0.75, help="practice speed in (0, 1]"
    )
    parser.add_argument("--preview", type=Path, help="write a practice WAV at the selected speed")
    parser.add_argument(
        "--preview-voice",
        choices=PREVIEW_VOICES,
        default="harmonica",
        help="preview sound: recorded harmonica samples (default) or plain sine tone",
    )
    parser.add_argument(
        "--alternatives", type=int, default=0, metavar="N", help="number of additional choices"
    )
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument(
        "--no-separate",
        action="store_true",
        help="transcribe a clean solo source without source separation",
    )
    parser.add_argument("--pitch-backend", default="pyin", choices=("pyin", "crepe"))
    parser.add_argument("--start", type=float, default=0.0, help="audio excerpt start in seconds")
    parser.add_argument("--duration", type=float, help="audio excerpt length in seconds")
    parser.add_argument("--stem", choices=STEMS, default="vocals", help="melody's source stem")
    parser.add_argument("--separation-model", choices=MODELS, default="htdemucs")
    parser.add_argument(
        "--device", default="auto", help="separation device: auto, cpu, cuda or cuda:N"
    )
    parser.add_argument("--cache-dir", type=Path, help="directory for stems and model weights")
    parser.add_argument(
        "--no-cache", action="store_true", help="recompute stems without caching them"
    )
    args = parser.parse_args(arguments)
    if args.alternatives < 0:
        parser.error("--alternatives must be nonnegative")

    def progress(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    try:
        targets = [
            args.file,
            *([args.harmony_audio] if args.harmony_audio else []),
            *([args.output] if args.output else []),
            *([args.preview] if args.preview else []),
        ]
        for index, path in enumerate(targets):
            for other in targets[index + 1 :]:
                if path.resolve() == other.resolve() or (
                    path.exists() and other.exists() and path.samefile(other)
                ):
                    raise ValueError("input, output and preview paths must be different")
        practice = PracticeOptions(speed=args.practice_speed)
        preview_options = PreviewOptions(speed=args.practice_speed, voice=args.preview_voice)
        if args.chords or args.harmony_audio:
            if command == "transcribe":
                raise ValueError("chord mode arranges reviewed notes; transcribe a melody first")
            if args.start != 0 or args.duration is not None:
                raise ValueError("chord mode uses event timestamps; select an excerpt in the score")
            if args.harmony_audio:
                if args.file.suffix.lower() != ".json":
                    raise ValueError("--harmony-audio requires reviewed melody JSON as the input")
                from harptab.transcribe.harmony import harmonize
                from harptab.transcribe.load import load_audio

                reviewed = load_melody(args.file)
                progress(
                    "Checking harmony around reviewed notes; compare candidates with the source..."
                )
                score = harmonize(reviewed, load_audio(args.harmony_audio, 22050), 22050)
            else:
                score = load_score(args.file)
            chord_choices = search_chords(
                score,
                mode=args.mode,
                harps=args.harps,
                skill=args.skill,
                top_n=args.alternatives + 1,
                overblows=args.overblows,
            )
            if not chord_choices:
                raise ValueError("input contains no chord events")
            chord_arrangement = chord_choices[0]
            if args.format == "practice":
                chord_output = render_chord_practice(
                    score, chord_arrangement, options=practice, alternatives=chord_choices[1:]
                )
            elif args.format == "json":
                chord_output = render_chord_json(
                    score, chord_arrangement, alternatives=chord_choices[1:]
                )
            else:
                chord_output = render_chord_text(
                    score, chord_arrangement, alternatives=chord_choices[1:]
                )
            if args.preview:
                preview_chords_wav(args.preview, score, chord_arrangement, options=preview_options)
                progress(
                    f"Wrote {args.preview_voice} chord preview at {args.practice_speed:.0%} speed: "
                    f"{args.preview}"
                )
            if args.output:
                args.output.write_text(chord_output, encoding="utf-8", newline="\n")
            else:
                sys.stdout.write(chord_output)
            return 0
        if command == "transcribe" and args.format == "practice":
            raise ValueError(
                "a practice guide requires arrangement; use 'harptab FILE --format practice'"
            )
        separation = SeparationParams(
            model=args.separation_model,
            device=args.device,
            cache_dir=args.cache_dir,
            use_cache=not args.no_cache,
        )
        if command == "transcribe":
            arrangement = None
            melody = transcribe_audio(
                args.file,
                no_separate=args.no_separate,
                pitch_backend=args.pitch_backend,
                stem=args.stem,
                separation_params=separation,
                start=args.start,
                duration=args.duration,
                progress=progress,
            )
            output = json.dumps(melody.to_dict(), indent=2, allow_nan=False) + "\n"
        else:
            melody = load_melody(
                args.file,
                no_separate=args.no_separate,
                pitch_backend=args.pitch_backend,
                stem=args.stem,
                separation_params=separation,
                start=args.start,
                duration=args.duration,
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
            arrangement = choices[0]
            if args.format == "practice":
                output = render_practice(
                    melody, arrangement, options=practice, alternatives=choices[1:]
                )
            else:
                renderer = render_json if args.format == "json" else render_text
                output = renderer(melody, arrangement, alternatives=choices[1:])
        if args.preview:
            preview_wav(args.preview, melody, arrangement, options=preview_options)
            progress(
                f"Wrote {args.preview_voice} preview at {args.practice_speed:.0%} speed: "
                f"{args.preview}"
            )
        if args.output:
            args.output.write_text(output, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(output)
    except (OSError, ValueError, ImportError, NotImplementedError, EOFError) as error:
        print(f"harptab: {error}", file=sys.stderr)
        return 2
    return 0
