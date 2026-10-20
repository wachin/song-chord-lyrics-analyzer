#!/usr/bin/env python3
"""Reproducible chord benchmark harness over the GuitarSet corpus (Phase I P1).

This is developer tooling, not a shipped command: it lives in ``scripts/`` and
is never included in the wheel or exercised by ``songlab``. It exists because
the one recorded chord number (duration-weighted CSR on GuitarSet comping
takes) was produced by a gitignored harness and therefore could not be
reproduced from the repository.

What makes a run reproducible:

* the take list, annotation index and both file digests come from the
  committed manifest (``tests/fixtures/guitarset_comp_manifest.json``), so a
  different corpus is refused instead of silently measured;
* the hypothesis comes from the registered chord engine through its public
  ``analyze()`` call, and the reference from the JAMS ``chord`` namespace;
* scoring uses the package primitives only
  (:mod:`song_chord_lyrics_analyzer.evaluation.guitarset`);
* every row records the engine, decoder settings, wall time, real-time factor,
  peak RSS, environment and date.

Audio is never committed: GuitarSet is CC BY 4.0 but its comp-take audio is
462 MiB. Download it from Zenodo 10.5281/zenodo.3371780 and point
``--corpus-dir`` at the extracted files.

Usage::

    # one-time: pin the corpus that was actually downloaded
    python scripts/chord_benchmark.py --write-manifest tests/fixtures/guitarset_comp_manifest.json

    # full measured run (180 comp takes, ~17 min on the development machine)
    python scripts/chord_benchmark.py --limit 180

    # the majority smoother, for the validation comparison
    python scripts/chord_benchmark.py --decoder majority --out .cache/chords/benchmark-majority

    # refit the per-event confidence mapping and report it held out
    python scripts/chord_benchmark.py --fit-confidence --out .cache/chords/benchmark-confidence

The output directory holds ``per_take.jsonl`` (one row per take, appended as
the run advances, so an interrupted run resumes with ``--resume``),
``aggregate.json`` and ``aggregate.md``. A run also reports the confidence
calibration (bands, risk-coverage, Brier, ECE); ``--fit-confidence`` adds
``confidence_fit.json`` with the refitted logistic and its held-out result.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
import wave
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from song_chord_lyrics_analyzer.engines import chroma_baseline  # noqa: E402
from song_chord_lyrics_analyzer.engines.base import ChordAnalysisOptions, EngineKind  # noqa: E402
from song_chord_lyrics_analyzer.engines.registry import create_default_registry  # noqa: E402
from song_chord_lyrics_analyzer.evaluation.confidence import (  # noqa: E402
    EventOutcome,
    apply_fit,
    calibration_report,
    combine_reports,
    fit_logistic,
)
from song_chord_lyrics_analyzer.evaluation.guitarset import (  # noqa: E402
    ANNOTATION_VIEWS,
    GuitarSetTake,
    aggregate_scores,
    event_outcomes,
    load_manifest,
    read_jams_chords,
    score_take,
    sha256_file,
    verify_take_files,
)
from song_chord_lyrics_analyzer.metrics.adapters import chord_segments  # noqa: E402
from song_chord_lyrics_analyzer.utils.errors import InputError, SongLabError  # noqa: E402

#: JAMS chord namespace index for each reference view.
_VIEW_INDEX = {"instructed": 0, "performed": 1}

#: Corpus provenance recorded in the manifest. The download date is the one in
#: docs/DATASET.md (2026-09-29), not the date this script happens to run.
_CORPUS = {
    "dataset": "GuitarSet",
    "version": "1.1.0",
    "doi": "10.5281/zenodo.3371780",
    "license": "CC BY 4.0",
    "retrieved": "2026-09-29",
    "notes": (
        "Comping takes from the audio_mono-mic archive. Audio and the full JAMS "
        "stay in the gitignored cache; only this manifest (take names, digests) "
        "is committed. Reference view 'instructed' reads JAMS chord index 0, "
        "'performed' reads index 1; the two are never mixed in one number."
    ),
}

DEFAULT_MANIFEST = ROOT / "tests" / "fixtures" / "guitarset_comp_manifest.json"


def _wav_duration(path: Path) -> float:
    """Duration of an uncompressed PCM WAV, from its header frames."""
    with wave.open(str(path), "rb") as reader:
        frame_rate = reader.getframerate()
        frames = reader.getnframes()
    if frame_rate <= 0:
        raise InputError(f"WAV file {path} reports a non-positive frame rate.")
    return frames / float(frame_rate)


def _corpus_files(corpus_dir: Path) -> list[tuple[GuitarSetTake, Path, Path]]:
    """Every ``*_comp`` take in ``corpus_dir`` as (take, audio, jams)."""
    jams_files = sorted(corpus_dir.glob("*_comp.jams"))
    if not jams_files:
        raise InputError(
            f"No GuitarSet comp takes found in {corpus_dir}.",
            hint=(
                "Extract audio_mono-mic.zip and annotation.zip into the directory "
                "(the files are named <take>_mic.wav and <take>.jams)."
            ),
        )
    entries: list[tuple[GuitarSetTake, Path, Path]] = []
    for jams_path in jams_files:
        name = jams_path.stem
        audio_path = corpus_dir / f"{name}_mic.wav"
        if not audio_path.exists():
            raise InputError(
                f"GuitarSet JAMS {jams_path.name} has no matching audio {audio_path.name}.",
                hint="Extract the audio archive next to the annotations, not into a subdirectory.",
            )
        entries.append(
            (
                GuitarSetTake(
                    name=name,
                    split="comp",
                    audio=audio_path.name,
                    jams=jams_path.name,
                    audio_sha256=sha256_file(audio_path),
                    jams_sha256=sha256_file(jams_path),
                    duration_seconds=round(_wav_duration(audio_path), 6),
                ),
                audio_path,
                jams_path,
            )
        )
    return entries


def write_manifest(corpus_dir: Path, path: Path) -> None:
    """Pin every comp take in ``corpus_dir`` into a committed manifest."""
    entries = _corpus_files(corpus_dir)
    document = dict(_CORPUS)
    document["takes"] = [
        {
            "name": take.name,
            "split": take.split,
            "audio": take.audio,
            "jams": take.jams,
            "audio_sha256": take.audio_sha256,
            "jams_sha256": take.jams_sha256,
            "duration_seconds": take.duration_seconds,
        }
        for take, _audio, _jams in entries
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    audio_mib = sum(audio.stat().st_size for _take, audio, _jams in entries) / (1024 * 1024)
    print(f"wrote {path}: {len(entries)} comp takes, {audio_mib:.1f} MiB of audio pinned")


def _environment(engine: Any) -> dict[str, str]:
    """Environment provenance: what ran this measurement and with what."""

    def version(distribution: str) -> str:
        try:
            return importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            return "not installed"

    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    info = engine.engine_info()
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "engine": info.name,
        "engine_version": info.version,
        "numpy": version("numpy"),
        "librosa": version("librosa"),
        "soundfile": version("soundfile"),
        "git_commit": commit,
    }


def _coerce_option(raw: str) -> Any:
    """``true``/``false`` become bools, integers ints, decimals floats, rest str."""
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _parse_options(pairs: Sequence[str]) -> dict[str, Any]:
    """Parse repeated ``KEY=VALUE`` engine options into a dict.

    Values are coerced so ``--option harmonic=true`` reaches the engine as a
    bool and ``--option change_penalty=0.5`` as a float; anything else stays a
    string. A pair without ``=`` or with an empty key is refused, because a
    silently ignored option would make a run unreproducible.
    """
    options: dict[str, Any] = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator or not key.strip():
            raise InputError(
                f"Engine option {pair!r} is not KEY=VALUE.",
                hint="Example: --option tuning=estimate, --option harmonic=true",
            )
        options[key.strip()] = _coerce_option(value.strip())
    return options


def _done_takes(jsonl_path: Path) -> set[str]:
    """Take names already present in a JSONL run file."""
    if not jsonl_path.exists():
        return set()
    done: set[str] = set()
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        try:
            done.add(str(json.loads(line)["take"]))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return done


def _confidence_markdown(confidence: dict[str, Any]) -> list[str]:
    """The calibration and risk-coverage tables for the run report."""
    if not confidence:
        return []
    lines = ["", "### Confidence calibration", ""]
    if confidence.get("accuracy") is None or confidence.get("ece") is None:
        lines.append("No event reported a confidence, so there is nothing to calibrate.")
        return lines
    lines.extend(
        [
            "| Reported band | Events | Duration (s) | Accuracy | Mean confidence |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for band, values in confidence["bands"].items():
        if not values["events"] or values["accuracy"] is None:
            continue
        lines.append(
            f"| {band} | {values['events']} | {values['seconds']:.1f} | "
            f"{values['accuracy']:.3f} | {values['mean_confidence']:.3f} |"
        )
    lines.extend(
        [
            "",
            f"Overall accuracy {confidence['accuracy']:.4f}; "
            f"Brier {confidence['brier']:.4f}; "
            f"expected calibration error {confidence['ece']:.4f}; "
            f"events without a confidence {confidence['unknown_events']} "
            f"({confidence['unknown_seconds']:.1f} s).",
            "",
            "### Risk–coverage",
            "",
            "| Confidence at least | Coverage | Accuracy |",
            "| --- | --- | --- |",
        ]
    )
    for threshold, values in confidence["thresholds"].items():
        accuracy = "—" if values["accuracy"] is None else f"{values['accuracy']:.3f}"
        lines.append(f"| {threshold} | {values['coverage']:.3f} | {accuracy} |")
    return lines


def _markdown(aggregate: dict[str, Any]) -> str:
    """A table for docs/ENGINE_COMPARISON.md from the aggregate."""
    settings = aggregate["settings"]
    environment = aggregate["environment"]
    lines = [
        "| Metric | Mean | Median | Min | Max |",
        "| --- | --- | --- | --- | --- |",
    ]
    labels = {
        "csr": "Duration CSR (raw)",
        "csr_triads": "Duration CSR (triad-reduced, both sides)",
        "segment_overlap": "Segment overlap (MIREX mean)",
        "change_precision": "Change precision",
        "change_recall": "Change recall",
        "change_f1": "Change F1",
        "timing_reference_to_hypothesis": "Median boundary error, ref → hyp (s)",
        "timing_hypothesis_to_reference": "Median boundary error, hyp → ref (s)",
        "hypothesis_chords": "Hypothesis chords per take",
        "hypothesis_segments": "Hypothesis segments per take",
    }
    for key, label in labels.items():
        summary = aggregate["metrics"].get(key)
        if not summary:
            continue
        lines.append(
            f"| {label} | {summary['mean']:.4f} | {summary['median']:.4f} | "
            f"{summary['min']:.4f} | {summary['max']:.4f} |"
        )
    reference = aggregate["metrics"].get("reference_chords")
    if reference:
        lines.append(
            f"| Reference chords per take | {reference['mean']:.2f} | — | "
            f"{reference['min']} | {reference['max']} |"
        )
    per_take = f"{aggregate['metrics']['count']} takes"
    run_line = (
        f"**Run:** {per_take}, reference view `{settings['reference']}`, "
        f"engine `{environment['engine']}` {environment['engine_version']}, "
        f"decoder `{settings['decoder']}`, change penalty {settings['change_penalty']}, "
        f"change window {settings['change_window']} s."
    )
    engine_options = settings.get("engine_options") or {}
    if engine_options:
        rendered = ", ".join(
            f"`{key}={str(value).lower() if isinstance(value, bool) else value}`"
            for key, value in sorted(engine_options.items())
        )
        run_line += f" Engine options: {rendered}."
    lines.extend(
        [
            "",
            run_line,
            f"**Environment:** {environment['platform']}, CPython {environment['python']}, "
            f"numpy {environment['numpy']}, librosa {environment['librosa']}, "
            f"commit {environment['git_commit']}.",
            f"**Date:** {aggregate['date']} (UTC). "
            f"Peak RSS high-water {aggregate['totals']['peak_rss_bytes'] / (1024 * 1024):.1f} MB, "
            f"total decode wall {aggregate['totals']['processing_seconds']:.1f} s.",
        ]
    )
    lines.extend(_confidence_markdown(aggregate.get("confidence") or {}))
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> int:
    """Run the requested measurement and write the output files."""
    manifest = load_manifest(args.manifest)
    takes = manifest.subset(split="comp")[: args.limit]
    registry = create_default_registry()
    engine = registry.get(EngineKind.CHORDS, args.engine)
    if not engine.is_available():
        raise InputError(
            f"Engine {args.engine!r} is not available in this environment.",
            hint='Install the DSP extra: pip install -e ".[dev,dsp]"',
        )

    if args.fit_confidence and args.resume:
        raise InputError(
            "--fit-confidence cannot resume a run: a fit needs every take's events.",
            hint=(
                "Drop --resume (or start a fresh --out directory) so the fit sees the whole corpus."
            ),
        )

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "per_take.jsonl"
    done = _done_takes(jsonl_path) if args.resume else set()
    if not args.resume and jsonl_path.exists():
        raise InputError(
            f"Output already exists: {jsonl_path}",
            hint="Pass --resume to continue it, or choose a different --out directory.",
        )

    # Explicit --option pairs win over the dedicated flags when both name the
    # same key, and the run records the effective value rather than the flag's.
    extra: dict[str, Any] = {
        "decoder": args.decoder,
        "change_penalty": args.change_penalty,
        **_parse_options(args.option),
    }
    options = ChordAnalysisOptions(extra=extra)
    environment = _environment(engine)
    started = time.time()
    processed = skipped = 0
    outcomes_by_take: dict[str, list[EventOutcome]] = {}
    with jsonl_path.open("a", encoding="utf-8") as jsonl:
        for index, take in enumerate(takes, 1):
            if take.name in done:
                print(f"[{index:3d}/{len(takes)}] {take.name:28s} already measured")
                continue
            if args.budget_seconds and processed and time.time() - started > args.budget_seconds:
                print(
                    f"budget of {args.budget_seconds:.0f}s reached; rerun with --resume to continue"
                )
                break
            try:
                audio_path, jams_path = verify_take_files(
                    take, args.corpus_dir, check_hashes=not args.no_verify
                )
            except InputError as error:
                if not args.allow_missing:
                    raise
                print(f"[{index:3d}/{len(takes)}] {take.name:28s} skipped: {error.message}")
                skipped += 1
                continue
            reference = read_jams_chords(jams_path, index=_VIEW_INDEX[args.reference])
            take_started = time.perf_counter()
            result = engine.analyze(audio_path, options)
            wall = time.perf_counter() - take_started
            performance = result.metadata.get("performance")
            if not isinstance(performance, dict):
                performance = {}
            audio_seconds = performance.get("audio_seconds")
            hypothesis = chord_segments(
                result.chords,
                end=float(audio_seconds) if isinstance(audio_seconds, (int, float)) else None,
            )
            row: dict[str, Any] = {
                "take": take.name,
                "split": take.split,
                "reference": args.reference,
                "audio_seconds": round(float(audio_seconds), 3)
                if isinstance(audio_seconds, (int, float))
                else None,
                "decoder": extra["decoder"],
                "change_penalty": extra["change_penalty"],
                "engine": result.engine,
                "engine_version": result.engine_version,
                "wall_seconds": round(wall, 3),
                "peak_rss_bytes": performance.get("peak_rss_bytes"),
                "real_time_factor": performance.get("real_time_factor"),
            }
            row.update(score_take(reference, hypothesis, change_window=args.change_window))
            outcomes = event_outcomes(reference, result.chords)
            row["confidence"] = calibration_report(outcomes)
            if args.fit_confidence:
                outcomes_by_take[take.name] = outcomes
            jsonl.write(json.dumps(row, allow_nan=False) + "\n")
            jsonl.flush()
            processed += 1
            print(
                f"[{index:3d}/{len(takes)}] {take.name:28s} "
                f"csr={row['csr']:.3f} csr_tri={row['csr_triads']:.3f} "
                f"f1={row['change_f1']:.3f} ({wall:.1f}s)"
            )

    rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    if not rows:
        print("no takes measured; nothing written")
        return 1
    aggregate = {
        "manifest": str(args.manifest.relative_to(ROOT))
        if args.manifest.is_relative_to(ROOT)
        else str(args.manifest),
        "manifest_sha256": sha256_file(args.manifest),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "settings": {
            "reference": args.reference,
            "decoder": extra["decoder"],
            "change_penalty": extra["change_penalty"],
            "change_window": args.change_window,
            "corpus_verified": not args.no_verify,
            "engine_options": {
                key: value
                for key, value in extra.items()
                if key not in {"decoder", "change_penalty"}
            },
        },
        "environment": environment,
        "metrics": aggregate_scores(rows),
        "confidence": combine_reports([row["confidence"] for row in rows if row.get("confidence")]),
        "totals": {
            "processing_seconds": round(sum(float(row["wall_seconds"]) for row in rows), 3),
            "peak_rss_bytes": max(
                (int(row["peak_rss_bytes"]) for row in rows if row.get("peak_rss_bytes")),
                default=0,
            ),
        },
    }
    (out_dir / "aggregate.json").write_text(
        json.dumps(aggregate, indent=1) + "\n", encoding="utf-8"
    )
    (out_dir / "aggregate.md").write_text(_markdown(aggregate), encoding="utf-8")

    metrics = aggregate["metrics"]
    summary = (
        f"\n{metrics['count']} takes  "
        f"csr={metrics['csr']['mean']:.4f}  "
        f"csr_triads={metrics['csr_triads']['mean']:.4f}  "
        f"overlap={metrics['segment_overlap']['mean']:.4f}  "
        f"change_f1={metrics['change_f1']['mean']:.4f}"
    )
    timing = metrics.get("timing_reference_to_hypothesis")
    if timing:
        summary += f"  timing={timing['mean']:.3f}s"
    print(summary)
    confidence = aggregate["confidence"]
    if confidence and confidence.get("accuracy") is not None:
        print(
            f"confidence: brier={confidence['brier']:.4f} ece={confidence['ece']:.4f} "
            f"unknown={confidence['unknown_events']} events"
        )
    if args.fit_confidence:
        _fit_and_write(takes, outcomes_by_take, out_dir)
    print(f"wrote {out_dir / 'per_take.jsonl'}, aggregate.json, aggregate.md")
    print(f"processed={processed} skipped={skipped} elapsed={time.time() - started:.0f}s")
    return 0


def _fit_and_write(
    takes: Sequence[GuitarSetTake],
    outcomes_by_take: dict[str, list[EventOutcome]],
    out_dir: Path,
) -> None:
    """Refit the margin-to-confidence logistic and record train/held-out results.

    The split is the manifest's own order: even-indexed takes train, odd-indexed
    takes are held out. It is deterministic, it needs no random seed, and the
    held-out half never influences the constants it is scored with.
    """
    train: list[EventOutcome] = []
    heldout: list[EventOutcome] = []
    train_takes = heldout_takes = 0
    for index, take in enumerate(takes):
        events = outcomes_by_take.get(take.name)
        if not events:
            continue
        if index % 2 == 0:
            train.extend(events)
            train_takes += 1
        else:
            heldout.extend(events)
            heldout_takes += 1
    if not train or not heldout:
        raise InputError(
            "--fit-confidence needs at least two measured takes (one for each split).",
            hint="Run the whole corpus, not --limit 1.",
        )
    fit = fit_logistic(train)
    trained = calibration_report(apply_fit(train, fit))
    tested = calibration_report(apply_fit(heldout, fit))
    report = {
        "split": (
            "even-indexed manifest takes fitted, odd-indexed takes held out; "
            "the fit weights each event by its duration"
        ),
        "train": {
            "takes": train_takes,
            "events": fit.events,
            "seconds": round(fit.seconds, 3),
            "slope": round(fit.slope, 4),
            "intercept": round(fit.intercept, 4),
            "iterations": fit.iterations,
            "converged": fit.converged,
            "report": combine_reports([trained]),
        },
        "heldout": {"takes": heldout_takes, "report": combine_reports([tested])},
        "engine": {
            "name": chroma_baseline.ENGINE_NAME,
            "slope": chroma_baseline.CONFIDENCE_SLOPE,
            "intercept": chroma_baseline.CONFIDENCE_INTERCEPT,
        },
    }
    (out_dir / "confidence_fit.json").write_text(
        json.dumps(report, indent=1) + "\n", encoding="utf-8"
    )
    heldout_report = report["heldout"]["report"]
    print(
        f"confidence fit: slope={fit.slope:.4f} intercept={fit.intercept:.4f} "
        f"({train_takes} takes trained, converged={fit.converged})"
    )
    if not fit.converged:
        print(
            "warning: the fit did not converge (perfectly separable or too little "
            "data); do not copy these constants into the engine."
        )
    print(
        f"held out ({heldout_takes} takes): accuracy={heldout_report['accuracy']:.4f} "
        f"brier={heldout_report['brier']:.4f} ece={heldout_report['ece']:.4f}"
    )
    print(
        "engine constants: "
        f"slope={chroma_baseline.CONFIDENCE_SLOPE} "
        f"intercept={chroma_baseline.CONFIDENCE_INTERCEPT}"
    )
    print(f"wrote {out_dir / 'confidence_fit.json'}")


def build_parser() -> argparse.ArgumentParser:
    """The command line."""
    parser = argparse.ArgumentParser(
        prog="chord_benchmark.py",
        description=(
            "Measure the registered chord engine on the committed GuitarSet "
            "comp manifest with the audit section 11 comparison vector."
        ),
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path(".cache/chords/guitarset"),
        help="directory holding the downloaded <take>.jams and <take>_mic.wav files",
    )
    parser.add_argument(
        "--reference",
        choices=ANNOTATION_VIEWS,
        default="instructed",
        help="JAMS chord annotation to score against (never mixed in one number)",
    )
    parser.add_argument("--engine", default="chroma-baseline")
    parser.add_argument("--decoder", choices=("viterbi", "majority"), default="viterbi")
    parser.add_argument("--change-penalty", type=float, default=0.80)
    parser.add_argument(
        "--option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "engine option, repeatable (e.g. --option tuning=estimate; "
            "--option harmonic=true); overrides --decoder/--change-penalty"
        ),
    )
    parser.add_argument(
        "--change-window",
        type=float,
        default=0.5,
        help="tolerance in seconds for a change-point match",
    )
    parser.add_argument("--limit", type=int, default=None, help="measure at most N takes")
    parser.add_argument(
        "--budget-seconds",
        type=float,
        default=None,
        help="stop after this many seconds; the JSONL is resumable",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory (default .cache/chords/benchmark/<timestamp>)",
    )
    parser.add_argument("--resume", action="store_true", help="skip takes already in the JSONL")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="skip missing files instead of aborting the run",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="skip SHA-256 verification (not reproducible; for local experiments only)",
    )
    parser.add_argument(
        "--fit-confidence",
        action="store_true",
        help=(
            "refit the margin-to-confidence logistic on even-indexed takes and "
            "report it on the odd-indexed ones (writes confidence_fit.json)"
        ),
    )
    parser.add_argument(
        "--write-manifest",
        type=Path,
        default=None,
        metavar="PATH",
        help="pin the comp takes found in --corpus-dir into a committed manifest and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point: pin a manifest, or run the measurement."""
    args = build_parser().parse_args(argv)
    if args.out is None:
        args.out = Path(".cache/chords/benchmark") / datetime.now().strftime("%Y-%m-%d-%H%M%S")
    try:
        if args.write_manifest is not None:
            write_manifest(args.corpus_dir, args.write_manifest)
            return 0
        return run(args)
    except SongLabError as error:
        print(f"error: {error.message}", file=sys.stderr)
        if error.hint:
            print(f"hint: {error.hint}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
