"""Shared data contracts. Pitches are MIDI integers; times are seconds."""

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class NoteEvent:
    pitch: int
    start: float
    duration: float
    confidence: float = 1.0
    cents_offset: float = 0.0


@dataclass(frozen=True)
class KeyEstimate:
    tonic: int
    mode: str
    confidence: float


@dataclass
class Melody:
    notes: list[NoteEvent]
    tempo_bpm: float | None = None
    beats: list[float] | None = None
    key_estimate: KeyEstimate | None = None
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation, with times in seconds."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Melody":
        """Read the documented melody schema; omitted optional fields use defaults."""
        fields = dict(data)
        fields["notes"] = [NoteEvent(**note) for note in fields["notes"]]
        if fields.get("key_estimate") is not None:
            fields["key_estimate"] = KeyEstimate(**fields["key_estimate"])
        return cls(**fields)


class Technique(Enum):
    BLOW = "blow"
    DRAW = "draw"
    DRAW_BEND = "draw_bend"
    BLOW_BEND = "blow_bend"
    OVERBLOW = "overblow"
    OVERDRAW = "overdraw"


@dataclass(frozen=True)
class Action:
    hole: int
    technique: Technique
    bend_semitones: int = 0
    pitch: int = 0


@dataclass(frozen=True)
class Arrangement:
    harp_key: int
    position: int
    transpose: int
    actions: list[Action | None]
    cost: float
    stats: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible actions with string-valued techniques."""
        result = asdict(self)
        result["actions"] = [
            None if action is None else {**asdict(action), "technique": action.technique.value}
            for action in self.actions
        ]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Arrangement":
        """Restore actions and their technique enums from JSON data."""
        fields = dict(data)
        fields["actions"] = [
            None
            if action is None
            else Action(**{**action, "technique": Technique(action["technique"])})
            for action in fields["actions"]
        ]
        return cls(**fields)
