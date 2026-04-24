"""Tests for run_omr_via_pipeline — the bridge used by /analyze."""

from pathlib import Path

import pytest

from app.omr.audiveris_runner import AudiverisError, OmrResult
from app.pipeline.run import run_omr_via_pipeline

# Minimal valid MusicXML — must contain at least one part with one note,
# otherwise the OMR stage's broken-XML validator will reject it.
_MIN_VALID_XML = (
    "<score-partwise>"
    "<part-list><score-part id='P1'/></part-list>"
    "<part id='P1'><measure number='1'>"
    "<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration></note>"
    "</measure></part>"
    "</score-partwise>"
)


def test_run_returns_full_omr_result(tmp_path):
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")

    expected = OmrResult(
        music_xml=_MIN_VALID_XML,
        measures=[],
        page_sizes=[(595.0, 842.0)],
        warnings=["something benign"],
    )

    def fake_driver(_p: Path, out: Path) -> OmrResult:
        # Audiveris would have written here; our fake just confirms the
        # caller created the directory.
        assert out.exists()
        return expected

    got = run_omr_via_pipeline(pdf, tmp_path / "out", driver=fake_driver)
    # The legacy shape — measures + page_sizes — must round-trip through
    # the pipeline so /analyze still has data for the PDF overlay.
    assert got.music_xml == expected.music_xml
    assert got.page_sizes == expected.page_sizes
    assert got.warnings == expected.warnings


def test_run_aborted_pipeline_raises(tmp_path):
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"")

    def crashing(_p, _o):
        raise AudiverisError("fake NPE")

    # The helper must not swallow the failure: /analyze relies on this to
    # turn into a 500.
    with pytest.raises(RuntimeError, match="AudiverisError"):
        run_omr_via_pipeline(pdf, tmp_path / "out", driver=crashing)


def test_run_creates_pipeline_artifacts_subdir(tmp_path):
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"")

    def fake_driver(_p, _o):
        return OmrResult(music_xml=_MIN_VALID_XML, measures=[])

    out = tmp_path / "out"
    run_omr_via_pipeline(pdf, out, driver=fake_driver)
    # Pipeline artifacts go under <out>/_pipeline/<job_id>/...
    assert (out / "_pipeline").exists()
    assert any((out / "_pipeline").iterdir())
