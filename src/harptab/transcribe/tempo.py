"""Beat tracking is deferred to the rhythm-display milestone."""

from collections.abc import Sequence


def estimate_tempo(audio: Sequence[float], sr: int) -> tuple[float, list[float]]:
    """Return tempo in BPM and beat times in seconds (planned for M3)."""
    raise NotImplementedError("beat tracking is planned for M3")
