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


@dataclass(frozen=True)
class ChordEvent:
    """Simultaneous target pitches; melody_pitch must survive a reduced voicing.

    None selects the highest pitch as the melody. Times are source seconds.
    """

    pitches: tuple[int, ...]
    start: float
    duration: float
    confidence: float = 1.0
    melody_pitch: int | None = None

    @property
    def lead(self) -> int:
        return max(self.pitches) if self.melody_pitch is None else self.melody_pitch


@dataclass
class ChordScore:
    """Sorted, non-overlapping chord events, including single-note events."""

    events: list[ChordEvent]
    tempo_bpm: float | None = None
    beats: list[float] | None = None
    key_estimate: KeyEstimate | None = None
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for event in result["events"]:
            event["pitches"] = list(event["pitches"])
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChordScore":
        fields = dict(data)
        fields["events"] = [
            ChordEvent(**{**event, "pitches": tuple(event["pitches"])})
            for event in fields["events"]
        ]
        if fields.get("key_estimate") is not None:
            fields["key_estimate"] = KeyEstimate(**fields["key_estimate"])
        return cls(**fields)


@dataclass(frozen=True)
class Voicing:
    """One single-hole action or a contiguous group of unbent, same-breath holes."""

    actions: tuple[Action, ...]


@dataclass(frozen=True)
class ChordArrangement:
    harp_key: int
    position: int
    transpose: int
    voicings: list[Voicing | None]
    cost: float
    stats: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["voicings"] = [
            None
            if voicing is None
            else {
                "actions": [
                    {**asdict(action), "technique": action.technique.value}
                    for action in voicing.actions
                ]
            }
            for voicing in self.voicings
        ]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChordArrangement":
        fields = dict(data)
        fields["voicings"] = [
            None
            if voicing is None
            else Voicing(
                tuple(
                    Action(**{**action, "technique": Technique(action["technique"])})
                    for action in voicing["actions"]
                )
            )
            for voicing in fields["voicings"]
        ]
        return cls(**fields)
