# Gemini CLI instructions

The canonical repository instructions are in [`AGENTS.md`](AGENTS.md). Read it
first, then [`docs/AGENT_ONBOARDING.md`](docs/AGENT_ONBOARDING.md),
[`ROADMAP.md`](ROADMAP.md) §1 and the relevant phase.

Setup and gate:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,gui]"
python scripts/check.py
```

Never import or modify `external/`; never commit private audio/lyrics, model
weights, virtual environments or caches; do not invent measurements. Keep GUI
logic in `app/`. Update the roadmap marker in the same change.

This file is only a pointer; edit `AGENTS.md` for rules.
