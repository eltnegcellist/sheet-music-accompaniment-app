"""Tests for the optional homr OMR adapter and engine selection."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from app.omr import engine as omr_engine
from app.omr import homr_runner
from app.omr.engine import configured_driver, configured_engine
from app.omr.homr_runner import HomrError, run_homr
from app.omr.result import OmrResult
from app.pipeline.artifacts import FileArtifactStore
from app.pipeline.contracts import ArtifactRef, StageInput
from app.pipeline.run import run_omr_via_pipeline
from app.pipeline.stages.omr import make_test_stage

FIXTURE = Path(__file__).parent / "fixtures" / "fake_homr.py"


def _fake_render(
    _pdf: Path,
    pages_dir: Path,
    *,
    page_count: int,
    dpi: int,
) -> list[Path]:
    assert dpi == 300
    pages_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for page in range(1, page_count + 1):
        path = pages_dir / f"page_{page:04d}.png"
        path.write_bytes(b"fake png")
        paths.append(path)
    return paths


def test_run_homr_merges_page_musicxml(tmp_path, monkeypatch):
    pdf = tmp_path / "score.pdf"
    pdf.write_bytes(b"%PDF fake")
    monkeypatch.setattr(
        homr_runner,
        "_page_sizes",
        lambda _path: [(595.0, 842.0), (595.0, 842.0)],
    )
    monkeypatch.setattr(homr_runner, "count_pages", lambda _path: 2)
    monkeypatch.setattr(homr_runner, "_render_pdf_pages", _fake_render)
    monkeypatch.setenv("HOMR_COMMAND", f"{sys.executable} {FIXTURE}")

    result = run_homr(pdf, tmp_path / "out")

    assert result.page_sizes == [(595.0, 842.0), (595.0, 842.0)]
    assert result.measures == []
    assert 'measure number="2"' in result.music_xml
    assert any("PDF連動小節ハイライト" in w for w in result.warnings)


def test_run_homr_salvages_output_from_nonzero_exit(tmp_path, monkeypatch):
    pdf = tmp_path / "score.pdf"
    pdf.write_bytes(b"%PDF fake")
    monkeypatch.setattr(homr_runner, "_page_sizes", lambda _path: [(1.0, 1.0)])
    monkeypatch.setattr(homr_runner, "count_pages", lambda _path: 1)
    monkeypatch.setattr(homr_runner, "_render_pdf_pages", _fake_render)
    monkeypatch.setenv("HOMR_COMMAND", f"{sys.executable} {FIXTURE}")
    monkeypatch.setenv("FAKE_HOMR_EXIT", "7")

    result = run_homr(pdf, tmp_path / "out")

    assert result.music_xml
    assert any("code 7" in warning for warning in result.warnings)


def test_missing_homr_command_is_clear(monkeypatch):
    monkeypatch.delenv("HOMR_COMMAND", raising=False)
    monkeypatch.setattr(homr_runner.shutil, "which", lambda _name: None)
    with pytest.raises(HomrError, match="homr command not found"):
        homr_runner._homr_command()


def test_engine_defaults_to_audiveris(monkeypatch):
    monkeypatch.delenv("OMR_ENGINE", raising=False)
    assert configured_engine(None) == "audiveris"


def test_engine_selects_homr_from_params(monkeypatch):
    monkeypatch.delenv("OMR_ENGINE", raising=False)
    params = {
        "omr": {
            "engine": "homr",
            "homr": {
                "dpi": 240,
                "timeout_sec": 90,
                "coreml_encoder": False,
            },
        }
    }
    assert configured_engine(params) == "homr"
    assert configured_driver(params).keywords == {
        "dpi": 240,
        "timeout_sec": 90,
        "coreml_encoder": False,
    }


def test_homr_stage_uses_homr_metric_namespace(tmp_path):
    pdf = tmp_path / "input.pdf"
    pdf.write_bytes(b"%PDF fake")
    store = FileArtifactStore(root=tmp_path / "artifacts", job_id="job")
    store.put(ArtifactRef(kind="input_pdf", path=str(pdf)))

    xml = (
        "<score-partwise><part-list><score-part id='P1'/></part-list>"
        "<part id='P1'><measure number='1'><note><pitch><step>C</step>"
        "<octave>4</octave></pitch><duration>1</duration></note></measure>"
        "</part></score-partwise>"
    )
    stage = make_test_stage(
        lambda _pdf, _out: OmrResult(music_xml=xml, measures=[]),
        engine="homr",
    )
    output = stage(
        StageInput(
            job_id="job",
            image_id="page_0",
            params={},
            artifacts=store,
            trace={},
        )
    )
    assert output.status == "ok"
    assert output.metrics.fields["omr.homr.valid_xml"] is True


def test_run_helper_selects_homr_from_params(tmp_path, monkeypatch):
    pdf = tmp_path / "input.pdf"
    pdf.write_bytes(b"%PDF fake")
    xml = (
        "<score-partwise><part-list><score-part id='P1'/></part-list>"
        "<part id='P1'><measure number='1'><note><pitch><step>C</step>"
        "<octave>4</octave></pitch><duration>1</duration></note></measure>"
        "</part></score-partwise>"
    )
    calls: list[tuple[int, int, bool | None]] = []

    def fake_homr(
        _pdf: Path,
        _out: Path,
        *,
        dpi: int,
        timeout_sec: int,
        coreml_encoder: bool | None,
    ) -> OmrResult:
        calls.append((dpi, timeout_sec, coreml_encoder))
        return OmrResult(music_xml=xml, measures=[], warnings=["from homr"])

    monkeypatch.delenv("OMR_ENGINE", raising=False)
    monkeypatch.setattr(omr_engine, "run_homr", fake_homr)
    result = run_omr_via_pipeline(
        pdf,
        tmp_path / "out",
        params={
            "omr": {
                "engine": "homr",
                "homr": {
                    "dpi": 240,
                    "timeout_sec": 90,
                    "coreml_encoder": True,
                },
            }
        },
    )

    assert calls == [(240, 90, True)]
    assert result.warnings == ["from homr"]
