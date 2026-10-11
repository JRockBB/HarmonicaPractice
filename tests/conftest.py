"""Shared public-domain fixtures and small melody constructors."""

import json
from pathlib import Path

import pytest

from harptab.models import Melody

FIXTURES = Path(__file__).parent / "fixtures" / "melodies"


@pytest.fixture(params=sorted(FIXTURES.glob("*.melody.json")), ids=lambda path: path.stem)
def melody_fixture(request: pytest.FixtureRequest) -> tuple[Path, Melody]:
    path = request.param
    return path, Melody.from_dict(json.loads(path.read_text(encoding="utf-8")))
