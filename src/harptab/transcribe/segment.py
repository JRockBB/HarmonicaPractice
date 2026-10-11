"""Convert voiced pitch contours to stable monophonic notes without audio dependencies."""

from dataclasses import dataclass
from math import atan2, cos, floor, isfinite, isnan, log2, pi, sin
from statistics import median

from harptab.models import NoteEvent
from harptab.transcribe.pitch import PitchTrack


@dataclass(frozen=True)
class SegmentParams:
    min_duration: float = 0.08  # Minimum note length in seconds.
    min_confidence: float = 0.5  # Minimum voiced probability.
    pitch_jump: float = 0.7  # Sustained semitone change that starts a note.
    change_hold: float = 0.045  # Seconds a pitch change must persist before splitting.
    median_frames: int = 5  # Odd median-filter width, in frames.
    history: float = 0.2  # Seconds of recent pitch used as the stable note reference.
    bridge_gap: float = 0.012  # Maximum brief dropout to bridge in seconds.
    onset_scoop: float = 0.1  # Maximum initial scoop duration to absorb into the next note.
    correct_tuning: bool = True  # Remove estimated global sub-semitone tuning before rounding.


def _validate(track: PitchTrack, params: SegmentParams) -> None:
    if not len(track.times) == len(track.f0_hz) == len(track.voiced_prob):
        raise ValueError("pitch-track arrays must have equal lengths")
    previous = -1.0
    for time, hz, confidence in zip(track.times, track.f0_hz, track.voiced_prob, strict=True):
        if not isfinite(time) or time < 0 or time <= previous:
            raise ValueError("frame times must be finite, nonnegative and strictly increasing")
        if not isnan(hz) and (not isfinite(hz) or hz < 0):
            raise ValueError("frequencies must be positive, zero or NaN for unvoiced frames")
        if not isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("voiced probabilities must be finite and in 0..1")
        previous = time
    for name in ("min_duration", "pitch_jump", "change_hold", "history"):
        value = getattr(params, name)
        if not isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    for name in ("bridge_gap", "onset_scoop"):
        value = getattr(params, name)
        if not isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and nonnegative")
    if not isfinite(params.min_confidence) or not 0 <= params.min_confidence <= 1:
        raise ValueError("min_confidence must be in 0..1")
    if (
        type(params.median_frames) is not int
        or params.median_frames < 1
        or params.median_frames % 2 != 1
    ):
        raise ValueError("median_frames must be a positive odd integer")


def _tuning(values: list[float]) -> float:
    # Circular statistics handle a +40-cent drift whose vibrato crosses the rounding boundary.
    center = atan2(sum(sin(2 * pi * v) for v in values), sum(cos(2 * pi * v) for v in values)) / (
        2 * pi
    )
    offset = median(v - floor(v - center + 0.5) for v in values)
    return (offset + 0.5) % 1 - 0.5


def segment(track: PitchTrack, params: SegmentParams | None = None) -> list[NoteEvent]:
    """Segment f0 frames into notes in seconds, retaining original cents deviation as metadata.

    The final frame extends by the median frame interval. The pipeline clips this
    estimate to the recording length. Fewer than two frames cannot establish a duration.
    """
    p = params or SegmentParams()
    _validate(track, p)
    if len(track.times) < 2:
        return []
    times = list(track.times)
    hop = median(b - a for a, b in zip(times, times[1:], strict=False))
    edges = times + [times[-1] + hop]
    pitches: list[float | None] = [
        69 + 12 * log2(hz / 440)
        if isfinite(hz) and hz > 0 and confidence >= p.min_confidence
        else None
        for hz, confidence in zip(track.f0_hz, track.voiced_prob, strict=True)
    ]
    # Bridge only very short gaps with matching pitch on both sides.
    i = 0
    while i < len(pitches):
        if pitches[i] is not None:
            i += 1
            continue
        end = i + 1
        while end < len(pitches) and pitches[end] is None:
            end += 1
        before = pitches[i - 1] if i else None
        after = pitches[end] if end < len(pitches) else None
        if (
            before is not None
            and after is not None
            and edges[end] - edges[i] <= p.bridge_gap
            and abs(before - after) < p.pitch_jump
        ):
            pitches[i:end] = [(before + after) / 2] * (end - i)
        i = end
    voiced_values = [value for value in pitches if value is not None]
    if not voiced_values:
        return []
    tuning = _tuning(voiced_values) if p.correct_tuning else 0.0
    result: list[NoteEvent] = []
    start = 0
    while start < len(pitches):
        if pitches[start] is None:
            start += 1
            continue
        end = start + 1
        while end < len(pitches) and pitches[end] is not None:
            end += 1
        raw = [float(value) for value in pitches[start:end] if value is not None]
        radius = p.median_frames // 2
        smooth = [
            median(raw[max(0, j - radius) : min(len(raw), j + radius + 1)]) for j in range(len(raw))
        ]
        boundaries = [0]
        pending: int | None = None
        direction = 0
        history_frames = max(1, round(p.history / hop))
        for j in range(1, len(smooth)):
            anchor_end = pending if pending is not None else j
            anchor_start = max(boundaries[-1], anchor_end - history_frames)
            anchor = median(smooth[anchor_start:anchor_end])
            delta = smooth[j] - anchor
            if abs(delta) >= p.pitch_jump:
                sign = 1 if delta > 0 else -1
                if pending is None or sign != direction:
                    pending, direction = j, sign
                if edges[start + j + 1] - edges[start + pending] >= p.change_hold:
                    boundaries.append(pending)
                    pending = None
            else:
                pending = None
        boundaries.append(len(raw))
        # An initial short pitch excursion is an onset ornament, not a separate note.
        if len(boundaries) > 2 and edges[start + boundaries[1]] - edges[start] < p.onset_scoop:
            boundaries.pop(1)
        for left, right in zip(boundaries, boundaries[1:], strict=False):
            begin, finish = edges[start + left], edges[start + right]
            if finish - begin < p.min_duration:
                continue
            center = median(raw[left:right])
            pitch = floor(center - tuning + 0.5)
            confidence = sum(track.voiced_prob[start + left : start + right]) / (right - left)
            if not 0 <= pitch <= 127 or confidence < p.min_confidence:
                continue
            result.append(
                NoteEvent(pitch, begin, finish - begin, confidence, (center - pitch) * 100)
            )
        start = end
    return result
