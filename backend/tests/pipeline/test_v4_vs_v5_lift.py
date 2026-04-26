"""End-to-end lift: v4_with_pitch vs v5_real_pdf.

v5 = v4 + fix_key_accidentals + fill_measures (already in v4 inherited).
The point is to prove that the user's reported pain (dropped accidentals
+ measure gaps) measurably improves under v5 without regressing the
existing happy path.
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


def test_v5_lifts_dropped_key_accidentals_above_v4(tmp_path):
    s_v4 = _run_under("v4_with_pitch", "10_audiveris_dropped_key_accidentals.musicxml", tmp_path)
    s_v5 = _run_under("v5_real_pdf", "10_audiveris_dropped_key_accidentals.musicxml", tmp_path)
    assert s_v5 > s_v4, f"v4={s_v4:.4f} v5={s_v5:.4f}"


@pytest.mark.parametrize(
    "fixture",
    [
        "01_clean_4_4_C_major.musicxml",
        "05_piano_two_staves.musicxml",
        "09_audiveris_offscale_outlier.musicxml",
    ],
)
def test_v5_does_not_regress_on_clean_or_v4_handled(tmp_path, fixture):
    """Inputs that v4 already handled must not regress under v5."""
    s_v4 = _run_under("v4_with_pitch", fixture, tmp_path)
    s_v5 = _run_under("v5_real_pdf", fixture, tmp_path)
    assert s_v5 >= s_v4 - 0.005, f"{fixture}: v4={s_v4:.4f} v5={s_v5:.4f}"
