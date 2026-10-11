import ast
import subprocess
import sys
from pathlib import Path


def test_core_and_render_import_no_heavy_modules() -> None:
    forbidden = {
        "numpy",
        "scipy",
        "librosa",
        "torch",
        "torchcrepe",
        "demucs",
        "demucs_infer",
        "soundfile",
        "basic_pitch",
        "music21",
        "mido",
    }
    root = Path(__file__).parents[1] / "src" / "harptab"
    paths = [
        root / "models.py",
        *root.joinpath("core").glob("*.py"),
        *root.joinpath("render").glob("*.py"),
    ]
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                assert not {name.name.split(".")[0] for name in node.names} & forbidden
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden
    script = (
        "import sys; import harptab; import harptab.render.text; import harptab.render.json; "
        "import harptab.cli; import harptab.pipeline; "
        f"assert not ({{name.split('.')[0] for name in sys.modules}} & {forbidden!r})"
    )
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
