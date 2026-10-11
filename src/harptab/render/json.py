"""Machine-readable output using the frozen shared contracts."""

import json
from collections.abc import Sequence
from typing import Any

from harptab.models import Arrangement, Melody


def render_json(
    melody: Melody,
    arrangement: Arrangement,
    *,
    alternatives: Sequence[Arrangement] = (),
) -> str:
    """Serialize a melody and arrangement, plus optional alternative arrangements."""
    if len(melody.notes) != len(arrangement.actions):
        raise ValueError("arrangement must have one action per melody note")
    data: dict[str, Any] = {"melody": melody.to_dict(), "arrangement": arrangement.to_dict()}
    if alternatives:
        data["alternatives"] = [a.to_dict() for a in alternatives]
    return json.dumps(data, indent=2, allow_nan=False) + "\n"
