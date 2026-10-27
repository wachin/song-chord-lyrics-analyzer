# GitHub Copilot instructions

The canonical repository rules are in [`AGENTS.md`](../AGENTS.md). Read it and
[`docs/AGENT_ONBOARDING.md`](../docs/AGENT_ONBOARDING.md) before suggesting or
changing code.

- Install `.[dev,gui]` for the gate; `.[dev]` alone cannot type-check `gui/`.
- Run `python scripts/check.py` before proposing a change as complete.
- Never import or modify `external/`; it is reference-only third-party material.
- Never commit private songs, user lyrics, model weights, `.venv*`, caches or
  generated results. Use generated fixtures for audio.
- GUI widgets read `app/` and `SongSession`; analysis algorithms stay out of
  `gui/`.
- Update the roadmap marker and its status in the same change.
- No benchmark or accuracy number without a measured environment and date.

Keep this file a short pointer; the rules live in `AGENTS.md`.
