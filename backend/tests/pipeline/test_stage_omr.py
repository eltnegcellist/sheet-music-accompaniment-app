"""Tests for the OMR pipeline stage with a fake Audiveris driver.

We never invoke the real JVM/CLI in tests — the stage is wired with a
callable that returns a pre-baked `OmrResult`, so the tests exercise the
contract translation (metrics, artifacts, status mapping) only.
"""

import io
from pathlib import Path

from app.omr.audiveris_runner import AudiverisError, OmrResult
from app.pipeline import (
    EventLogger,
    FileArtifactStore,
    Pipeline,
    StageInput,
    StageOutput,
    StageRegistry,
)
from app.pipeline.contracts import ArtifactRef
from app.pipeline.stages.omr import make_test_stage


def _setup_job(tmp_path):
    pdf = tmp_path / "input.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    store = FileArtifactStore(root=tmp_path / "artifacts", job_id="job1")
    store.put(ArtifactRef(kind="input_pdf", path=str(pdf)))
    return store


def test_ok_path_emits_musicxml_and_metrics(tmp_path):
    store = _setup_job(tmp_path)

    def fake_driver(pdf: Path, out_dir: Path) -> OmrResult:
        assert pdf.exists()
        assert out_dir.exists()
        return OmrResult(
            music_xml=(
                "<score-partwise>"
                "<part-list><score-part id='P1'/></part-list>"
                "<part id='P1'><measure number='1'>"
                "<note><pitch><step>C</step><octave>4</octave></pitch>"
                "<duration>4</duration></note>"
                "</measure></part>"
                "</score-partwise>"
            ),
            measures=[],
            page_sizes=[(595.0, 842.0)],
            warnings=[],
        )

    stage = make_test_stage(fake_driver)
    inp = StageInput(
        job_id="job1",
        image_id="page_0",
        params={},
        artifacts=store,
        trace={},
    )
    out = stage(inp)
    assert out.status == "ok"
    assert out.metrics.fields["omr.audiveris.valid_xml"] is True
    assert out.metrics.fields["omr.audiveris.page_count"] == 1
    musicxml = store.get("musicxml")
    assert musicxml is not None
    assert "<score-partwise>" in Path(musicxml.path).read_text(encoding="utf-8")


def test_audiveris_error_becomes_failed(tmp_path):
    store = _setup_job(tmp_path)

    def fake_driver(_pdf, _out):
        raise AudiverisError("simulated NPE")

    stage = make_test_stage(fake_driver)
    out = stage(
        StageInput(job_id="j", image_id="page_0", params={}, artifacts=store, trace={})
    )
    assert out.status == "failed"
    assert "simulated NPE" in (out.error or "")


def test_empty_musicxml_becomes_failed(tmp_path):
    store = _setup_job(tmp_path)

    def fake_driver(_pdf, _out):
        return OmrResult(music_xml="", measures=[])

    stage = make_test_stage(fake_driver)
    out = stage(
        StageInput(job_id="j", image_id="page_0", params={}, artifacts=store, trace={})
    )
    assert out.status == "failed"
    assert "no MusicXML" in (out.error or "")


def test_missing_pdf_artifact_fails(tmp_path):
    # A fresh store with no `input_pdf` registered.
    store = FileArtifactStore(root=tmp_path / "art", job_id="j")
    stage = make_test_stage(
        lambda _p, _o: OmrResult(music_xml="<x/>", measures=[])
    )
    out = stage(
        StageInput(job_id="j", image_id="page_0", params={}, artifacts=store, trace={})
    )
    assert out.status == "failed"
    assert "input_pdf" in (out.error or "")


def test_validator_flags_broken_xml_as_failed(tmp_path):
    store = _setup_job(tmp_path)

    # Audiveris-style "I returned XML, but it has zero parts" failure.
    def fake_driver(_p, _o):
        return OmrResult(music_xml="<score-partwise><part-list/></score-partwise>", measures=[])

    stage = make_test_stage(fake_driver)
    out = stage(
        StageInput(job_id="j", image_id="page_0", params={}, artifacts=store, trace={})
    )
    assert out.status == "failed"
    assert "no_parts" in (out.error or "")
    # Validator's first issue code is recorded for log aggregation.
    assert out.metrics.fields.get("omr.audiveris.failure_class") == "omr.no_parts"
    # The metrics still reflect the validator's counts so report.md can show them.
    assert out.metrics.fields["omr.audiveris.measure_count"] == 0


def test_pipeline_runs_stage_end_to_end(tmp_path):
    store = _setup_job(tmp_path)
    reg = StageRegistry()
    reg.register(
        "omr.audiveris",
        make_test_stage(
            lambda _p, _o: OmrResult(
                music_xml=(
                    "<score-partwise>"
                    "<part-list><score-part id='P1'/></part-list>"
                    "<part id='P1'><measure number='1'>"
                    "<note><pitch><step>C</step><octave>4</octave></pitch>"
                    "<duration>4</duration></note>"
                    "</measure></part>"
                    "</score-partwise>"
                ),
                measures=[],
                page_sizes=[(1, 1)],
            )
        ),
    )
    pipe = Pipeline(
        job_id="job1",
        store=store,
        logger=EventLogger(sink=io.StringIO()),
        registry=reg,
        param_set_id="v1_baseline@deadbeef",
    )
    res = pipe.run(["omr.audiveris"], params={})
    assert res.aborted is False
    assert res.outputs[-1][1].status == "ok"
