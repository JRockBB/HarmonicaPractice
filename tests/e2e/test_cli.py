import json
import subprocess
import sys
from pathlib import Path

import pytest

from harptab.models import Melody
from scripts.fixtures_to_midi import write_midi


def run_cli(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "harptab", *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_json_and_midi_cli(melody_fixture: tuple[Path, Melody], tmp_path: Path) -> None:
    path, melody = melody_fixture
    midi = tmp_path / "input.mid"
    write_midi(melody, midi)
    for source in (path, midi):
        result = run_cli("arrange", source, "--harps", "C", "--format", "json")
        assert result.returncode == 0, result.stderr
        output = json.loads(result.stdout)
        assert len(output["arrangement"]["actions"]) == len(melody.notes)
        assert output["arrangement"]["transpose"] == 0
        assert output["arrangement"]["harp_key"] == 0


def test_output_and_rearrange(tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_text('{"notes":[{"pitch":48,"start":0,"duration":1}]}')
    output = tmp_path / "output.json"
    result = run_cli(
        path,
        "--mode",
        "practice",
        "--harps",
        "c,Bb,F#",
        "--alternatives",
        2,
        "--format",
        "json",
        "-o",
        output,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert len(json.loads(output.read_text())["alternatives"]) == 2
    again = run_cli("arrange", output, "--harps", "C")
    assert again.returncode == 0, again.stderr
    assert "Harp: C" in again.stdout


@pytest.mark.parametrize(
    "content",
    [
        "null",
        "{",
        '{"notes":[]}',
        '{"notes":[{"pitch":60,"start":0,"duration":-1}]}',
        '{"notes":[{"pitch":"C4","start":0,"duration":1}]}',
    ],
)
def test_bad_input_is_friendly(content: str, tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(content)
    result = run_cli(path)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert not result.stdout


def test_missing_audio_and_bad_keys(tmp_path: Path) -> None:
    path = tmp_path / "song.wav"
    for args, message in [
        ((path,), "does not exist"),
        (("transcribe", path), "does not exist"),
        ((path, "--harps", "H"), "invalid harp key"),
        ((path, "--stem", "lead"), "invalid choice"),
        ((path, "--device", "mps"), "separation device"),
    ]:
        result = run_cli(*args)
        assert result.returncode == 2
        assert message in result.stderr
        assert "Traceback" not in result.stderr


@pytest.mark.parametrize("command", ["transcribe", "arrange"])
def test_cli_passes_separation_options(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from harptab import cli
    from harptab.models import NoteEvent

    def load(path: Path, **kwargs: object) -> Melody:
        assert kwargs["stem"] == "other"
        assert not kwargs["no_separate"]
        config = kwargs["separation_params"]
        assert config.cache_dir == tmp_path
        assert config.device == "cpu"
        assert config.model == "htdemucs_ft"
        assert not config.use_cache
        kwargs["progress"]("Separating test input...")
        return Melody([NoteEvent(72, 0, 1)])

    monkeypatch.setattr(cli, "transcribe_audio" if command == "transcribe" else "load_melody", load)
    assert (
        cli.main(
            [
                command,
                "song.wav",
                "--stem",
                "other",
                "--device",
                "cpu",
                "--cache-dir",
                str(tmp_path),
                "--no-cache",
                "--separation-model",
                "htdemucs_ft",
                "--format",
                "json",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert json.loads(captured.out)
    assert "Separating test input" in captured.err


@pytest.mark.parametrize("name,key", [("b", 11), ("bb", 10), ("B", 11), ("Cb", 11), ("f#", 6)])
def test_harp_key_spelling(name: str, key: int, tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_text('{"notes":[{"pitch":72,"start":0,"duration":1}]}')
    result = run_cli(path, "--harps", name, "--format", "json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["arrangement"]["harp_key"] == key
