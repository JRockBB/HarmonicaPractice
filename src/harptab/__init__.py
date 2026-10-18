"""Pure Python harmonica arrangement, with optional input adapters."""

from harptab.core.assign import assign
from harptab.core.chords import assign_chords, search_chords
from harptab.core.instrument import HarmonicaModel
from harptab.core.search import search
from harptab.models import (
    Action,
    Arrangement,
    ChordArrangement,
    ChordEvent,
    ChordScore,
    KeyEstimate,
    Melody,
    NoteEvent,
    Technique,
    Voicing,
)

__all__ = [
    "Action",
    "Arrangement",
    "ChordArrangement",
    "ChordEvent",
    "ChordScore",
    "HarmonicaModel",
    "KeyEstimate",
    "Melody",
    "NoteEvent",
    "Technique",
    "Voicing",
    "assign",
    "assign_chords",
    "search",
    "search_chords",
]
