"""WP8 source-separation boundary."""

from collections.abc import Sequence


def separate(audio: Sequence[float], sr: int, stem: str = "vocals") -> Sequence[float]:
    """Isolate a requested stem from audio sampled at ``sr`` Hz (planned for M2)."""
    raise NotImplementedError("source separation is planned for M2 (WP8)")
