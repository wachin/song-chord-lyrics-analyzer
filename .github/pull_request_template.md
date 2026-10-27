## What and why

<!-- One or two paragraphs. What changed, which user/developer problem it
solves, and why this layer/seam. -->

## Roadmap

- Section/task: <!-- e.g. ROADMAP §7 Phase F, "chart import" -->
- Marker before/after: <!-- [ ] -> [x], [ ] -> [~], etc. -->
- Missing part (for `[~]`): <!-- what did not land, and where it is tracked -->

## Verification

<!-- Paste the real result. Do not claim a pass you did not run. -->

```text
$ python scripts/check.py
...
```

- New/updated tests:
- Manual verification (if GUI/audio):
- Environment and date (if a measurement):

## Checklist

- [ ] The roadmap marker/status and any user-facing changelog/docs are updated.
- [ ] Tests cover the new path, including an edge/failure case; optional
      dependency tests skip rather than fail.
- [ ] `python scripts/check.py` passes (or the remaining failure is quoted).
- [ ] `external/` was not imported, copied, modified or added as a dependency.
- [ ] No private song/lyrics/screenshot, model weights, `.venv*`, caches or
      generated results are committed.
- [ ] Any accuracy/benchmark number includes its environment, date, command and
      manifest; no proprietary-app parity is claimed.
- [ ] GUI logic (if any) lives in `app/`, and the widget was verified offscreen.
