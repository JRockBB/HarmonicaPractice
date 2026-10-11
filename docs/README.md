# harptab

Turn any song into harmonica tabs.

Give `harptab` an audio file (MP3, WAV, FLAC, M4A) and it tells you which harmonica to pick up and which holes to play:

```
$ harptab song.mp3 --harps C,G,A

Song key:   E minor (estimated)
Use:        A harmonica, 2nd position (cross harp)
Difficulty: easy, 2 half-step bends

Verse
-4  -4  5  -5  6  -5  5  -4
4  -3'  -3  4  -4
...
```

## Why

Most harmonica tabs online are hand-made, inconsistent, and exist only for popular songs. Sheet music and MIDI files exist for even fewer songs. Nearly every song exists as an audio recording, so `harptab` starts from audio and works out the rest:

1. Pull the melody out of the recording.
2. Choose the harmonica key and position that make that melody easiest to play.
3. Assign each note to a hole and a breath direction (blow, draw, or bend) with as little jumping around as possible.
4. Print tabs a player can read.

## Scope

**In scope (v1)**
- Audio input in common formats.
- Symbolic input (MIDI, MusicXML) as a secondary path, mainly for testing and for users who have those files.
- 10-hole diatonic harmonica, Richter tuning, all 12 keys.
- Recommending harmonica key and position, with a difficulty score.
- Two modes:
  - **Play along**: keep the song's key, so you can play with the recording.
  - **Practice**: the song may be transposed to fit a harmonica you own.
- Plain-text tab output, plus JSON for other tools.

**Later**
- Rhythm and timing shown in the tab.
- Chromatic harmonica and alternate tunings (Country, Paddy Richter, Natural Minor).
- Web UI, PDF/HTML output, audio playback of the tab.
- Chords and double stops.

**Out of scope**
- Downloading or streaming songs. Users supply their own audio files.
- Distributing generated tabs of copyrighted songs. The tool runs locally on the user's own files.

## Status

The symbolic-to-tab implementation is available: melody JSON, MIDI, optional
MusicXML, harmonica search and assignment, text/JSON rendering, and a CLI.
Clean solo audio can now be transcribed using the audio extra and `--no-separate`.
Source separation and ML pitch backends remain planned. See the root [README](../README.md) for
working commands and [implementation plan](IMPLEMENTATION_PLAN.md) for decisions
and remaining milestones.

Design references:

- [`ARCHITECTURE.md`](ARCHITECTURE.md): pipeline, modules, data contracts.
- [`ROADMAP.md`](ROADMAP.md): phased work packages for coding agents.
- [`harmonica-reference.md`](harmonica-reference.md): the instrument model, tab notation, positions.
- [`AGENTS.md`](AGENTS.md): rules every coding agent follows in this repo.

## Language

Python 3.11+. The main reason is the audio side: source separation (Demucs), pitch tracking (pYIN via librosa, CREPE), and audio-to-MIDI (basic-pitch) are all Python-first. The harmonica core has no audio dependencies and is small enough to port to Julia or Rust later if wanted.
