"""``songlab export`` (roadmap Phase H): the command that writes the sheet.

The command owns format selection and sidecar folding - no rendering - so the
tests pin exactly that: the arguments, the formats the help names, the
effective (edited) layers being passed to the renderer when a sidecar sits
next to the audio file, and the message reporting the file written.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from song_chord_lyrics_analyzer.cli.commands import export
from song_chord_lyrics_analyzer.cli.main import build_parser, main
from song_chord_lyrics_analyzer.models.music import ChordEvent, ChordQuality
from song_chord_lyrics_analyzer.utils.errors import InputError


class TestArguments:
    def test_the_output_file_is_required_and_the_format_has_a_default(self) -> None:
        args = build_parser().parse_args(["export", "song.wav", "-o", "out.chordpro"])

        assert args.command == "export"
        assert args.audio == Path("song.wav")
        assert args.output == Path("out.chordpro")
        assert args.format == "chordpro"
        assert args.transpose is None
        assert args.simplify is False

    def test_the_transform_flags_are_accepted(self) -> None:
        args = build_parser().parse_args(
            ["export", "song.wav", "-o", "x", "--transpose", "-3", "--simplify"]
        )

        assert args.transpose == -3
        assert args.simplify is True

    def test_all_three_formats_are_accepted(self) -> None:
        for fmt in ("json", "chordpro", "markdown"):
            args = build_parser().parse_args(["export", "song.wav", "--format", fmt, "-o", "x"])
            assert args.format == fmt

    def test_the_command_is_in_the_command_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(["--help"])

        assert exit_info.value.code == 0
        assert "export" in capsys.readouterr().out


class TestSidecarFolding:
    def test_a_sidecar_next_to_the_audio_is_folded_in(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The exported chords are the sidecar's effective layer, not the engine's."""
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"riff-wave")
        captured: dict[str, Any] = {}

        def fake_run(path: Path, **options: Any) -> object:
            captured["path"] = path
            return SimpleNamespace(result="DOCUMENT")

        def fake_rebuild_stack(*d: Any, **o: Any) -> object:
            captured["folded"] = True
            return _FakeStack()

        def fake_export(document: Any, fmt: str, out: Path, **layers: Any) -> Path:
            captured["document"] = document
            captured["format"] = fmt
            captured["layers"] = layers
            out.write_text("sheet")
            return out

        monkeypatch.setattr(export, "run_analysis", fake_run)
        monkeypatch.setattr(export, "load_edits", lambda _path: "EDITS-DOC")
        monkeypatch.setattr(export, "rebuild_stack", fake_rebuild_stack)
        monkeypatch.setattr(export, "export_document", fake_export)
        (tmp_path / "song.songlab.json").write_text("{}")  # the sidecar exists

        out = tmp_path / "sheet.md"
        exit_code = export.run(
            build_parser().parse_args(
                ["export", str(audio), "--format", "markdown", "-o", str(out)]
            )
        )

        assert exit_code == 0
        assert captured["path"] == audio
        assert captured["document"] == "DOCUMENT"
        assert captured["format"] == "markdown"
        # The effective (edited) layers, not the document's raw ones: the
        # fake stack's event came through, and its empty lyric list was
        # falsy, so the document's lyrics were left to the renderer.
        layers = captured["layers"]
        assert [event.label for event in layers["chords"]] == ["D"]
        assert layers["lyrics"] is None

    def test_without_a_sidecar_the_layers_stay_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"riff-wave")
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            export, "run_analysis", lambda _p, **_o: SimpleNamespace(result="DOCUMENT")
        )
        monkeypatch.setattr(
            export,
            "export_document",
            lambda document, fmt, out, **layers: (
                captured.update(layers=layers, document=document) or out
            ),
        )
        out = tmp_path / "sheet.md"

        export.run(build_parser().parse_args(["export", str(audio), "-o", str(out)]))

        assert captured["layers"] == {"chords": None, "lyrics": None}

    def test_the_written_file_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"riff-wave")
        monkeypatch.setattr(
            export, "run_analysis", lambda _p, **_o: SimpleNamespace(result="DOCUMENT")
        )
        monkeypatch.setattr(
            export,
            "export_document",
            lambda document, fmt, out, **layers: (out.write_text("x"), out)[1],
        )
        out = tmp_path / "sheet.md"

        export.run(build_parser().parse_args(["export", str(audio), "-o", str(out)]))

        assert "Exported chordpro" in capsys.readouterr().out


class _FakeStack:
    """A CommandStack stand-in carrying one deliberately edited chord."""

    def __init__(self) -> None:
        # A user event whose evidence is real, so a transpose can move it:
        # label ``D`` at the same 0.0..1.0 span the fake document covers.
        self.effective: list[Any] = [
            ChordEvent(start=0.0, end=1.0, root="D", quality=ChordQuality.MAJOR, source="user")
        ]
        self.effective_lyrics: list[Any] = []


class _Document:
    """An AnalysisResult stand-in carrying only its chord layer."""

    def __init__(self, chords: list[ChordEvent]) -> None:
        self.chords = chords


class TestTransformFlags:
    """The CLI-first transpose workflow (Phase H): transform the export only."""

    @staticmethod
    def _base_chords() -> list[ChordEvent]:
        """The fake document's C, G, N, F layer (the phase D fixture's core)."""
        return [
            ChordEvent(start=0.0, end=1.0, root="C", quality=ChordQuality.MAJOR, source="fake"),
            ChordEvent(start=1.0, end=2.0, root="G", quality=ChordQuality.MAJOR, source="fake"),
            ChordEvent.silence(2.0, 3.0, source="fake"),
            ChordEvent(start=3.0, end=4.0, root="F", quality=ChordQuality.MAJOR, source="fake"),
        ]

    def _layers(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> tuple[Path, dict[str, Any]]:
        """A song, a captured ``export_document`` call, no sidecar."""
        audio = tmp_path / "song.wav"
        audio.write_bytes(b"riff-wave")
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            export,
            "run_analysis",
            lambda _p, **_o: SimpleNamespace(result=_Document(self._base_chords())),
        )

        def fake_export(document: Any, fmt: str, out: Path, **layers: Any) -> Path:
            captured["layers"] = layers
            out.write_text("x")
            return out

        monkeypatch.setattr(export, "export_document", fake_export)
        return audio, captured

    def test_transpose_composes_over_the_document_layer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        audio, captured = self._layers(monkeypatch, tmp_path)
        out = tmp_path / "sheet.md"

        assert (
            export.run(
                build_parser().parse_args(
                    ["export", str(audio), "-o", str(out), "--transpose", "2"]
                )
            )
            == 0
        )

        chords = captured["layers"]["chords"]
        assert [event.label for event in chords][:2] == ["D", "A"]  # C->D, G->A
        assert any(event.source == "user-transpose" for event in chords)
        assert captured["layers"]["lyrics"] is None  # no sidecar: nothing to change

    @pytest.mark.parametrize("offset", [-12, 12])
    def test_an_out_of_range_offset_is_rejected_before_anything_runs(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        offset: int,
    ) -> None:
        audio, _captured = self._layers(monkeypatch, tmp_path)
        out = tmp_path / "sheet.md"

        with pytest.raises(InputError, match=r"-11..\+11"):
            export.run(
                build_parser().parse_args(
                    ["export", str(audio), "-o", str(out), "--transpose", str(offset)]
                )
            )

    def test_simplify_and_transpose_compose_in_that_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        audio, captured = self._layers(monkeypatch, tmp_path)
        out = tmp_path / "sheet.md"

        export.run(
            build_parser().parse_args(
                ["export", str(audio), "-o", str(out), "--transpose", "2", "--simplify"]
            )
        )

        chords = captured["layers"]["chords"]
        assert [event.label for event in chords][:2] == ["D", "A"]

    def test_without_flags_the_saved_stack_is_passed_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        audio, captured = self._layers(monkeypatch, tmp_path)
        stack = _FakeStack()
        monkeypatch.setattr(export, "_saved_stack", lambda _audio: stack)
        out = tmp_path / "sheet.md"

        export.run(build_parser().parse_args(["export", str(audio), "-o", str(out)]))

        assert captured["layers"]["chords"] == stack.effective
        # An empty effective-lyric layer is falsy, so the document's own
        # lyrics win - the same truthiness rule the Phase G sidecar saver runs.
        assert captured["layers"]["lyrics"] is None

    def test_transpose_composes_over_saved_edits_not_instead_of_them(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        audio, captured = self._layers(monkeypatch, tmp_path)
        saved = _FakeStack()  # one saved event, labelled D
        monkeypatch.setattr(export, "_saved_stack", lambda _audio: saved)
        out = tmp_path / "sheet.md"

        export.run(
            build_parser().parse_args(["export", str(audio), "-o", str(out), "--transpose", "1"])
        )

        # Transposing the saved ``D`` event by one semitone more than the
        # base would: unrecognised evidence follows its own rule, but a bare
        # user event with a real quality moves.
        chords = captured["layers"]["chords"]
        assert len(chords) == 1
        # The saved ``D`` moved one semitone further - the flag composed over
        # the saved edit instead of replacing the saved layer.
        assert chords[0].root == "D#"
        assert chords[0].source == "user-transpose"
