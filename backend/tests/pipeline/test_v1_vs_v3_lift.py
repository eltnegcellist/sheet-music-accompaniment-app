"""End-to-end lift: v1_baseline vs v3_with_postprocess (W-05d).

Drives `run_omr_via_pipeline` with a fake Audiveris driver that returns
each broken fixture verbatim, then compares the resulting MusicXML
under two param sets: v1 (no postprocess) and v3 (postprocess on).

This is the production-shape simulation — same code path /analyze runs,
just with the JVM swapped for a static driver.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.omr.audiveris_runner import OmrResult
from app.pipeline.params_loader import load_params
from app.pipeline.run import run_omr_via_pipeline
from app.pipeline.scoring_facade import evaluate_musicxml_metrics


GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "golden"
PARAMS_DIR = Path(__file__).resolve().parents[2] / "params"
SCHEMA = PARAMS_DIR / "schema.json"


# Same broken fixtures the lift test uses; clean ones are excluded so a
# zero-lift assertion isn't muddied by perfect inputs.
BROKEN_FIXTURES = (
    "02_short_measure_one_beat_missing.musicxml",
    "03_long_measure_one_beat_extra.musicxml",
    "06_audiveris_dropped_two_beats.musicxml",
    "07_audiveris_split_chord.musicxml",
    "08_audiveris_drift_and_short.musicxml",
)


def _driver_for(xml: str):
    def _drv(_pdf: Path, _out: Path) -> OmrResult:
        return OmrResult(
            music_xml=xml,
            measures=[],
            page_sizes=[(595.0, 842.0)],
            warnings=[],
        )
    return _drv


def _final_score(xml: str) -> float:
    metrics = evaluate_musicxml_metrics(xml)
    assert metrics is not None
    return float(metrics["final_score"])


@pytest.mark.parametrize("fixture", BROKEN_FIXTURES)
def test_v3_lifts_score_above_v1(tmp_path, fixture):
    xml = (GOLDEN / fixture).read_text(encoding="utf-8")
    drv = _driver_for(xml)

    v1 = load_params("v1_baseline", PARAMS_DIR, schema_path=SCHEMA)
    v3 = load_params("v3_with_postprocess", PARAMS_DIR, schema_path=SCHEMA)

    pdf = tmp_path / "in.pdf"; pdf.write_bytes(b"")
    out_v1 = run_omr_via_pipeline(
        pdf, tmp_path / "v1",
        param_set_id=v1.param_set_id(),
        driver=drv,
        params=v1.data,
    )
    out_v3 = run_omr_via_pipeline(
        pdf, tmp_path / "v3",
        param_set_id=v3.param_set_id(),
        driver=drv,
        params=v3.data,
    )

    s_v1 = _final_score(out_v1.music_xml)
    s_v3 = _final_score(out_v3.music_xml)

    # On every broken fixture, v3 must beat v1 by a meaningful margin.
    assert s_v3 > s_v1 + 0.05, (
        f"{fixture}: v1={s_v1:.4f} v3={s_v3:.4f} (lift={s_v3-s_v1:+.4f})"
    )


def test_v3_average_lift_at_least_15_pct(tmp_path):
    v1 = load_params("v1_baseline", PARAMS_DIR, schema_path=SCHEMA)
    v3 = load_params("v3_with_postprocess", PARAMS_DIR, schema_path=SCHEMA)
    diffs: list[float] = []
    for fixture in BROKEN_FIXTURES:
        xml = (GOLDEN / fixture).read_text(encoding="utf-8")
        drv = _driver_for(xml)
        pdf = tmp_path / f"{fixture}.pdf"; pdf.write_bytes(b"")
        out_v1 = run_omr_via_pipeline(
            pdf, tmp_path / f"v1_{fixture}",
            param_set_id=v1.param_set_id(), driver=drv, params=v1.data,
        )
        out_v3 = run_omr_via_pipeline(
            pdf, tmp_path / f"v3_{fixture}",
            param_set_id=v3.param_set_id(), driver=drv, params=v3.data,
        )
        diffs.append(_final_score(out_v3.music_xml) - _final_score(out_v1.music_xml))
    avg = sum(diffs) / len(diffs)
    # Headline number for the docs: ≥ +0.15 average across broken inputs.
    assert avg >= 0.15, f"avg lift only {avg:+.4f}"
