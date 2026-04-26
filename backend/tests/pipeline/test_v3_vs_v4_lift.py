"""End-to-end lift test: v3_with_postprocess vs v4_with_pitch (S3-01-f).

Mirrors test_v1_vs_v3_lift.py one rung up: v4 = v3 + pitch_fix on.
Drives `run_omr_via_pipeline` with a fake Audiveris driver so we never
spin up the JVM.
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


def _driver_for(xml: str):
    def _drv(_pdf: Path, _out: Path) -> OmrResult:
        return OmrResult(
            music_xml=xml, measures=[], page_sizes=[(595.0, 842.0)], warnings=[]
        )
    return _drv


def _final_score(xml: str) -> float:
    metrics = evaluate_musicxml_metrics(xml)
    assert metrics is not None
    return float(metrics["final_score"])


def _run_under(param_set_name: str, fixture: str, tmp_path: Path) -> float:
    xml = (GOLDEN / fixture).read_text(encoding="utf-8")
    params = load_params(param_set_name, PARAMS_DIR, schema_path=SCHEMA)
    pdf = tmp_path / f"{param_set_name}_{fixture}.pdf"; pdf.write_bytes(b"")
    out_dir = tmp_path / f"{param_set_name}_{fixture}"
    res = run_omr_via_pipeline(
        pdf, out_dir,
        param_set_id=params.param_set_id(),
        driver=_driver_for(xml),
        params=params.data,
    )
    return _final_score(res.music_xml)


def test_v4_lifts_offscale_outlier_above_v3(tmp_path):
    # 09 has a single off-scale note (F# in C major) that v3 cannot
    # touch because v3 doesn't carry pitch_fix. v4 should catch it.
    s_v3 = _run_under("v3_with_postprocess", "09_audiveris_offscale_outlier.musicxml", tmp_path)
    s_v4 = _run_under("v4_with_pitch", "09_audiveris_offscale_outlier.musicxml", tmp_path)
    assert s_v4 > s_v3, f"v3={s_v3:.4f} v4={s_v4:.4f}"


@pytest.mark.parametrize(
    "fixture",
    [
        "01_clean_4_4_C_major.musicxml",
        "05_piano_two_staves.musicxml",
    ],
)
def test_v4_does_not_regress_on_clean_inputs(tmp_path, fixture):
    """Clean fixtures must not score worse under v4 than under v3."""
    s_v3 = _run_under("v3_with_postprocess", fixture, tmp_path)
    s_v4 = _run_under("v4_with_pitch", fixture, tmp_path)
    # Allow tiny float noise but reject any meaningful regression.
    assert s_v4 >= s_v3 - 0.005, f"{fixture}: v3={s_v3:.4f} v4={s_v4:.4f}"
