"""Local live-practice server; microphone audio stays inside the browser."""

import argparse
import json
import sys
import webbrowser
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from harptab.core.instrument import HarmonicaModel
from harptab.ingest.chords import score_from_melody
from harptab.models import Arrangement, ChordArrangement, ChordScore, Melody, Voicing
from harptab.render.chords import (
    omitted_pitches,
    render_chord_practice,
    voicing_instruction,
    voicing_token,
)
from harptab.render.practice import PracticeOptions, _note_name, action_instruction
from harptab.render.text import KEY_NAMES, action_token
from harptab.validation import validate_chord_arrangement

_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.mjs": ("app.mjs", "text/javascript; charset=utf-8"),
    "/pitch.mjs": ("pitch.mjs", "text/javascript; charset=utf-8"),
    "/engine.mjs": ("engine.mjs", "text/javascript; charset=utf-8"),
    "/takes.mjs": ("takes.mjs", "text/javascript; charset=utf-8"),
    "/review.mjs": ("review.mjs", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


def load_session(path: Path) -> dict[str, Any]:
    """Load a reviewed arrangement JSON, retaining actual voiced pitches and source seconds.

    Accepts the existing rendered melody or chord JSON contracts. A raw score must
    first be arranged with ``harptab arrange FILE --format json -o practice.json``.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "arrangement" not in data:
            raise ValueError("expected rendered arrangement JSON (use --format json)")
        if "score" in data:
            score = ChordScore.from_dict(data["score"])
            arrangement = ChordArrangement.from_dict(data["arrangement"])
        else:
            melody = Melody.from_dict(data["melody"])
            single = Arrangement.from_dict(data["arrangement"])
            score = score_from_melody(melody)
            arrangement = ChordArrangement(
                single.harp_key,
                single.position,
                single.transpose,
                [Voicing((a,)) if a else None for a in single.actions],
                single.cost,
                single.stats,
            )
        validate_chord_arrangement(score, arrangement)
        if not score.events:
            raise ValueError("arrangement contains no events")
        if len(score.events) > 10000:
            raise ValueError("choose an excerpt of at most 10,000 events")
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"{path.name}: invalid arrangement JSON") from error

    origin = score.events[0].start
    harp = HarmonicaModel(arrangement.harp_key)
    # Source names survive arrangement export; accept both Windows and POSIX paths.
    title = Path(score.source.replace("\\", "/")).stem if score.source else path.stem
    return {
        "title": title,
        "harp": KEY_NAMES[arrangement.harp_key],
        "transpose": arrangement.transpose,
        "fingerings": {
            str(pitch): [
                {"tab": action_token(action), "instruction": action_instruction(action)}
                for action in harp.actions_for_pitch(pitch)
            ]
            for pitch in range(128)
            if harp.actions_for_pitch(pitch)
        },
        "sourceStart": origin,
        "duration": score.events[-1].start + score.events[-1].duration - origin,
        "guide": render_chord_practice(score, arrangement, options=PracticeOptions(speed=0.5)),
        "events": [
            {
                "start": event.start - origin,
                "sourceStart": event.start,
                "duration": event.duration,
                "pitches": [a.pitch for a in voice.actions] if voice else [],
                "notes": [_note_name(a.pitch) for a in voice.actions] if voice else [],
                "actions": [
                    {
                        "hole": a.hole,
                        "technique": a.technique.value,
                        "bend_semitones": a.bend_semitones,
                        "pitch": a.pitch,
                    }
                    for a in voice.actions
                ]
                if voice
                else [],
                "tab": voicing_token(voice),
                "instruction": voicing_instruction(voice),
                "omitted": omitted_pitches(event, voice, arrangement.transpose),
            }
            for event, voice in zip(score.events, arrangement.voicings, strict=True)
        ],
    }


def make_server(sessions: Sequence[dict[str, Any]], port: int = 8765) -> ThreadingHTTPServer:
    """Bind a read-only, fixed-route practice server to IPv4 loopback (port 0 chooses a port)."""
    if not sessions:
        raise ValueError("provide at least one arrangement")
    payload = json.dumps({"sessions": list(sessions)}, allow_nan=False).encode("utf-8")
    assets = files("harptab").joinpath("assets", "listener")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            # Only loopback hosts are valid, including after DNS rebinding.
            bound_port = cast(ThreadingHTTPServer, self.server).server_port
            allowed = {f"127.0.0.1:{bound_port}", f"localhost:{bound_port}"}
            if self.headers.get("Host") not in allowed:
                self.send_error(403)
                return
            route = urlsplit(self.path).path
            if route == "/api/sessions":
                content, mime = payload, "application/json; charset=utf-8"
            elif route in _ASSETS:
                name, mime = _ASSETS[route]
                content = assets.joinpath(name).read_bytes()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Permissions-Policy", "microphone=(self), camera=()")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; media-src 'self' blob:; "
                "object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def listen_main(argv: Sequence[str]) -> int:
    """Run ``harptab listen arrangement.json [another.json]`` until Ctrl+C."""
    parser = argparse.ArgumentParser(prog="harptab listen", description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="reviewed arrangement JSON files")
    parser.add_argument("--port", type=int, default=8765, help="local port (default 8765)")
    parser.add_argument(
        "--no-browser", action="store_true", help="print the URL without opening it"
    )
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be in 0..65535")
    try:
        sessions = [load_session(path) for path in args.files]
        with make_server(sessions, args.port) as server:
            url = f"http://127.0.0.1:{server.server_port}/"
            print(f"Live practice: {url}\nPress Ctrl+C to stop.", flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as error:
        print(f"harptab listen: {error}", file=sys.stderr)
        return 2
    return 0
