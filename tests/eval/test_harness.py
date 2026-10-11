import builtins
import runpy
import sys
from pathlib import Path

import pytest


def test_harness_without_audio_reports_na(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = builtins.__import__

    def without_audio(name: str, *args: object, **kwargs: object) -> object:
        if name == "eval.metrics":
            raise ImportError("simulated missing optional dependencies")
        return original(name, *args, **kwargs)

    output = tmp_path / "baseline.md"
    monkeypatch.setattr(builtins, "__import__", without_audio)
    monkeypatch.setattr(sys, "argv", ["eval", "--output", str(output), "--variant", "clean"])
    with pytest.raises(SystemExit) as result:
        runpy.run_module("eval", run_name="__main__")
    assert result.value.code == 0
    text = output.read_text()
    assert text.count("| N/A | N/A | N/A | N/A | 100% | N/A |") == 7
    assert "uv sync --extra evaluation" in text
