"""The developer chart-check command: parse, align, report (no audio needed).

The pure parser and alignment are covered by ``test_chart_agreement.py``; this
test drives the script's wiring against a saved JSON result, which is the path a
user takes when they do not want to decode the song again.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(tmp_path: Path, *, as_json: bool = False) -> subprocess.CompletedProcess[str]:
    chart = tmp_path / "chart.txt"
    chart.write_text("[Intro]\nC G\nAm F\n", encoding="utf-8")
    result = tmp_path / "chords.json"
    result.write_text(
        json.dumps(
            {
                "engine": "chroma-baseline",
                "chords": [
                    {"label": "C", "start": 0.0, "end": 1.0},
                    {"label": "G", "start": 1.0, "end": 2.0},
                    {"label": "Am", "start": 2.0, "end": 3.0},
                    {"label": "F", "start": 3.0, "end": 4.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        str(ROOT / "scripts" / "chord_chart_check.py"),
        "--chart",
        str(chart),
        "--chords-json",
        str(result),
    ]
    if as_json:
        command.append("--json")
    return subprocess.run(command, capture_output=True, text=True, check=False, cwd=ROOT)


def test_the_command_reports_a_perfect_sequence(tmp_path: Path) -> None:
    completed = _run(tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert "Matched in order: 4 / 4 chart chords (100.0%)" in completed.stdout
    assert "Substitutions: 0" in completed.stdout
    assert "sequence agreement" in completed.stdout


def test_the_command_emits_machine_readable_alignment(tmp_path: Path) -> None:
    completed = _run(tmp_path, as_json=True)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["matched"] == 4
    assert payload["recall"] == 1.0
    assert payload["precision"] == 1.0
    assert payload["alignment"] == [
        {"chart": "C", "detected": "C", "kind": "match"},
        {"chart": "G", "detected": "G", "kind": "match"},
        {"chart": "Am", "detected": "Am", "kind": "match"},
        {"chart": "F", "detected": "F", "kind": "match"},
    ]
