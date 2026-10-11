# Harmonica reference

The domain knowledge `core/` encodes. Agents working on the arrangement half should treat this file as the spec.

## Diatonic, Richter tuning, key of C

| Hole | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Blow | C4 | E4 | G4 | C5 | E5 | G5 | C6 | E6 | G6 | C7 |
| Draw | D4 | G4 | B4 | D5 | F5 | A5 | B5 | D6 | F6 | A6 |

MIDI numbers: blow `[60, 64, 67, 72, 76, 79, 84, 88, 91, 96]`, draw `[62, 67, 71, 74, 77, 81, 83, 86, 89, 93]`.

A harmonica in key K is this table shifted by K semitones. Convention: keys G, Ab, A, Bb, B are pitched *below* C (shift −5..−1); Db, D, Eb, E, F, F# are *above* (shift +1..+6). Low and high tunings (Low F, High G) exist; support them as an optional shift override.

## Bends and over-notes

The rule: in each hole, the higher of the two reeds can be bent down toward the lower one, by up to one semitone less than the gap between them.

- **Holes 1–6:** draw is higher. Draw bends available:
  - 1: −1
  - 2: −1, −2
  - 3: −1, −2, −3
  - 4: −1
  - 5: none (gap is 1 semitone)
  - 6: −1
- **Holes 7–10:** blow is higher. Blow bends available:
  - 7: none
  - 8: −1
  - 9: −1
  - 10: −1, −2
- **Overblows** (holes 1, 4, 5, 6): one semitone above the draw note. C harp: 1o = Eb4, 4o = Eb5, 5o = F#5, 6o = Bb5.
- **Overdraws** (holes 7, 9, 10): one semitone above the blow note. C harp: 7o = C#6, 9o = G#6, 10o = C#7.

Derive all of these from the blow/draw tables and the gap rule rather than hard-coding them, so alternate tunings work automatically.

## Gaps

Without bends, a C harp is missing in the bottom octave (holes 1–3): C#, D#, F, F#, G#, A, A#. Draw bends supply all of these except D#4, which needs the hole 1 overblow. The middle octave (holes 4–7) is the full major scale. The top octave (holes 7–10) is missing B6, which needs the hole 10 half-step blow bend.

Hole 2 draw and hole 3 blow are the same pitch (G4). This is the main source of "two ways to play the same note" in the assigner.

## Positions

Position = which note of the harmonica you treat as home.

| Position | Home note (relative to harp key) | C harp plays in | Common use |
|---|---|---|---|
| 1st | +0 | C | Folk, melodies in major |
| 2nd ("cross harp") | +7 | G | Blues, rock, country. Most common. |
| 3rd | +2 | D | Minor, blues |
| 4th | +9 | A | Minor |
| 5th | +4 | E | Minor (Phrygian feel) |
| 12th | +5 | F | Major, less common |

General formula: home note = harp key + 7 × (n − 1) semitones, mod 12.

To pick a harp for a song in key S in position n: harp key = S − 7 × (n − 1), mod 12. Example: song in E, 2nd position, harp key = E − 7 = A.

## Tab notation (output format)

One token per note:

| Token | Meaning |
|---|---|
| `4` | blow hole 4 |
| `-4` | draw hole 4 |
| `-3'` | draw hole 3, bend down a half step |
| `-3''` | draw hole 3, bend down a whole step |
| `-3'''` | draw hole 3, bend down 1½ steps |
| `8'` | blow hole 8, bend down a half step |
| `4o` | overblow hole 4 |
| `7o` | overdraw hole 7 |
| `?` | note not playable on this harp (shown so the line keeps its shape) |

Separate tokens with spaces; line breaks mark phrases. This is the most common online convention. Some tab sources use `+4` for blow or `4b`/`4d`; support those as alternate output styles later if users ask.

## Test material

Use public-domain melodies (traditional folk tunes, hymns, nursery tunes) for fixtures. Their tabs are well known, which makes hand-checking easy. Do not commit commercial recordings or tabs copied from websites.
