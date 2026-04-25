"""Tests for the postprocess wiring inside run_omr_via_pipeline (W-01)."""

from pathlib import Path

from app.omr.audiveris_runner import OmrResult
from app.pipeline.run import run_omr_via_pipeline


_BROKEN = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure></part></score-partwise>"""

_PARAMS_WITH_POSTPROCESS = {
    "postprocess": {
        "rhythm_fix": {"enabled": True, "snap_durations": [1, 2, 4, 8, 16], "max_edits_per_measure": 4},
        "voice_rebuild": {"enabled": False},
    }
}


def _driver_returning(xml: str):
    def _drv(_pdf: Path, _out: Path) -> OmrResult:
        return OmrResult(
            music_xml=xml,
            measures=[],
            page_sizes=[(595.0, 842.0)],
            warnings=["preexisting"],
        )
    return _drv


# --- default behaviour preserved ---------------------------------------


def test_default_call_does_not_postprocess(tmp_path):
    pdf = tmp_path / "in.pdf"; pdf.write_bytes(b"")
    res = run_omr_via_pipeline(pdf, tmp_path / "out", driver=_driver_returning(_BROKEN))
    # No params -> XML returned verbatim. The opt-in keeps existing
    # callers (and existing tests) on the original code path.
    assert res.music_xml == _BROKEN
    assert "postprocess" not in " ".join(res.warnings)


# --- opt-in postprocess actually runs ----------------------------------


def test_opt_in_runs_postprocess(tmp_path):
    pdf = tmp_path / "in.pdf"; pdf.write_bytes(b"")
    res = run_omr_via_pipeline(
        pdf, tmp_path / "out",
        driver=_driver_returning(_BROKEN),
        params=_PARAMS_WITH_POSTPROCESS,
    )
    # The corrected XML differs from the broken input.
    assert res.music_xml != _BROKEN
    # Layout-side fields survive untouched so /analyze still has them.
    assert res.page_sizes == [(595.0, 842.0)]
    assert "preexisting" in res.warnings
    # An informative warning surfaced about the edits.
    assert any("postprocess applied" in w for w in res.warnings)


def test_postprocess_skipped_when_xml_empty(tmp_path):
    pdf = tmp_path / "in.pdf"; pdf.write_bytes(b"")
    drv = _driver_returning("")  # empty XML — Audiveris returned nothing

    # The OMR stage rejects empty XML upstream, so this raises. The
    # important thing is that postprocess wiring doesn't crash on an
    # empty-but-present music_xml in the same flow.
    try:
        run_omr_via_pipeline(
            pdf, tmp_path / "out",
            driver=drv,
            params=_PARAMS_WITH_POSTPROCESS,
        )
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError from empty OMR output")


def test_postprocess_failure_falls_back_to_omr(tmp_path):
    pdf = tmp_path / "in.pdf"; pdf.write_bytes(b"")
    # Malformed XML: the broken-XML validator in the OMR stage rejects
    # this before we get to postprocess. To exercise the postprocess
    # fallback path we use a structurally-valid but content-empty score.
    structurally_ok_but_unparseable_by_music21 = (
        "<score-partwise>"
        "<part-list><score-part id='P1'/></part-list>"
        "<part id='P1'><measure number='1'>"
        "<note><pitch><step>X</step><octave>4</octave></pitch><duration>4</duration></note>"
        "</measure></part></score-partwise>"
    )
    res = run_omr_via_pipeline(
        pdf, tmp_path / "out",
        driver=_driver_returning(structurally_ok_but_unparseable_by_music21),
        params=_PARAMS_WITH_POSTPROCESS,
    )
    # XML returned unchanged + a warning explains why postprocess didn't fire.
    assert res.music_xml == structurally_ok_but_unparseable_by_music21
    assert any("postprocess could not be applied" in w for w in res.warnings)


# --- both stages wired -------------------------------------------------


def test_voice_rebuild_only_also_works(tmp_path):
    pdf = tmp_path / "in.pdf"; pdf.write_bytes(b"")
    res = run_omr_via_pipeline(
        pdf, tmp_path / "out",
        driver=_driver_returning(_BROKEN),
        params={"postprocess": {"voice_rebuild": {"enabled": True}}},
    )
    # voice_rebuild on a non-piano single-staff score is a no-op but the
    # XML still round-trips through music21 → not necessarily byte-identical.
    assert res.music_xml  # didn't lose the score
