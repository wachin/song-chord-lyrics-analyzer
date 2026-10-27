# Claude Code instructions

The canonical repository instructions are in [`AGENTS.md`](AGENTS.md). Read it
before changing anything, then read [`docs/AGENT_ONBOARDING.md`](docs/AGENT_ONBOARDING.md),
[`ROADMAP.md`](ROADMAP.md) §1 and the phase you are touching.

Quick start:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,gui]"
python scripts/check.py
```

Hard boundaries: never import or modify `external/`; never add model weights,
private songs, user lyrics, `.venv*`, caches or generated results; no accuracy
number without a measured environment and date. GUI logic goes through `app/`.

Do not duplicate the rules here. If a rule needs to change, change `AGENTS.md`
and keep this file a pointer.
