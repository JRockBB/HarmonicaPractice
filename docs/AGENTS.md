# Instructions for coding agents

Read this before touching the repo. Then read `docs/ARCHITECTURE.md`, `docs/harmonica-reference.md`, and your work package in `docs/ROADMAP.md`.

## Ground rules

1. **Stay in your lane.** Only edit files your work package owns. If you need a change elsewhere, describe it in your final report.
2. **Contracts are frozen.** `src/harptab/models.py` and the data contracts in `docs/ARCHITECTURE.md` change only by explicit decision. If yours doesn't fit, stop and report; don't work around it with ad-hoc fields or dicts.
3. **Core stays pure.** Nothing under `src/harptab/core/`, `render/` or `models.py` may import numpy, librosa, torch, demucs, or any `[audio]` extra. A test enforces this.
4. **Domain facts come from `docs/harmonica-reference.md`.** If you believe the reference is wrong, say so in your report with reasoning; don't silently diverge.
5. **No copyrighted material in the repo.** No commercial recordings, no tabs or melodies copied from websites, no lyrics. Fixtures are public-domain tunes or synthesized audio. Users' own files go in git-ignored folders (`eval/local/`).

## Tooling

```bash
uv sync                     # core deps
uv sync --extra audio       # transcription stack
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest               # core tests
uv run pytest -m audio      # slow / heavy tests
```

A change is done only when format, lint, type-check and tests all pass.

## Code style

- Python ≥ 3.11, type hints everywhere, `mypy --strict` on `core/` and `models.py`.
- Small pure functions. Data in, data out. No global state; caches go through explicit objects.
- Musical quantities: MIDI note numbers (int) for pitches, pitch classes 0–11 for keys (0 = C), seconds (float) for time. Convert to note names only in `render/`.
- Tunable numbers (thresholds, costs) live in dataclasses with defaults and a one-line comment saying what they control. No magic numbers in function bodies.
- Docstrings on public functions: what it does, units of arguments, one example where useful.

## Testing

- Every behavior in your WP's "Done when" has a test.
- Core tests must be fast (< 1 s each) and run without the `[audio]` extra.
- Audio tests use synthesized signals generated in the test or by fixture scripts. Mark them `@pytest.mark.audio`.
- Prefer exact expected tabs for fixtures; prefer property tests for search/assignment invariants (e.g., play-along mode never transposes, every assigned action actually produces the target pitch).

## Reporting

End every task with a short report:

- What was built (files, public functions).
- Any deviation from ARCHITECTURE.md or ROADMAP.md, and why.
- Contract or cross-WP change requests.
- Open questions and known weaknesses.

## Commits

Small, focused commits with imperative subject lines (`Add Viterbi hole assignment`). One work package per branch.
