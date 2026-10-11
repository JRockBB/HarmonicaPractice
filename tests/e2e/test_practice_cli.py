import json
import wave
from pathlib import Path

import pytest

from harptab.cli import main
from harptab.models import Melody


def test_every_fixture_generates_instructions_and_preview(
    melody_fixture: tuple[Path, Melody], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, melody = melody_fixture
    guide = tmp_path / "practice.md"
    preview = tmp_path / "practice.wav"
    assert (
        main(
            [
                str(source),
                "--harps",
                "C",
                "--format",
                "practice",
                "--practice-speed",
                "0.5",
                "--preview",
                str(preview),
                "-o",
                str(guide),
            ]
        )
        == 0
    )
    text = guide.read_text(encoding="utf-8")
    assert "# Harmonica practice guide" in text
    assert "**C harmonica**" in text
    assert "**50% speed**" in text
    assert "preserves the source pitches" in text
    assert text.count("| Check pitch/timing |") == 0
    with wave.open(str(preview)) as audio:
        span = melody.notes[-1].start + melody.notes[-1].duration - melody.notes[0].start
        assert audio.getnframes() == round(span * 22050 / 0.5)
    captured = capsys.readouterr()
    assert not captured.out
    assert "Wrote reference-tone preview" in captured.err


@pytest.mark.parametrize("target", ["output", "preview", "same_targets"])
def test_output_collisions_preserve_input(target: str, tmp_path: Path) -> None:
    source = tmp_path / "song.json"
    data = '{"notes":[{"pitch":72,"start":0,"duration":0.1}]}'
    source.write_text(data)
    if target == "output":
        args = [str(source), "-o", str(source)]
    elif target == "preview":
        args = [str(source), "--preview", str(source)]
    else:
        output = tmp_path / "result.wav"
        args = [str(source), "-o", str(output), "--preview", str(output)]
    assert main(args) == 2
    assert source.read_text() == data


def test_json_remains_parseable_with_preview(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "song.json"
    source.write_text('{"notes":[{"pitch":72,"start":0,"duration":0.1}]}')
    assert main([str(source), "--format", "json", "--preview", str(tmp_path / "preview.wav")]) == 0
    assert json.loads(capsys.readouterr().out)["arrangement"]["transpose"] == 0


def test_invalid_practice_speed_and_command_fail(tmp_path: Path) -> None:
    source = tmp_path / "not-read.wav"
    assert main([str(source), "--practice-speed", "0"]) == 2
    assert main(["transcribe", str(source), "--format", "practice"]) == 2
