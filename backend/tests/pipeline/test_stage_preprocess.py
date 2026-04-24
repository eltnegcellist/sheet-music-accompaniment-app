"""Tests for preprocess.staff_norm.

We synthesise tiny grayscale arrays with known staff-line spacing so the
estimator's output is predictable, then verify both the pure functions
and the registered stage's behaviour.
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.pipeline.artifacts import FileArtifactStore
from app.pipeline.contracts import ArtifactRef, StageInput
from app.pipeline.stages.preprocess import (
    estimate_staff_space,
    quality_gate_pass,
    staff_norm_stage,
)


def _five_line_staff(spacing: int, width: int = 80, padding: int = 20) -> np.ndarray:
    """Build a synthetic image: 5 dark horizontal lines spaced `spacing` px apart."""
    height = padding * 2 + spacing * 4 + 1
    img = np.full((height, width), 255, dtype=np.uint8)
    for k in range(5):
        y = padding + k * spacing
        img[y, :] = 0
    return img.astype(np.float32)


def _save_png(arr: np.ndarray, path: Path) -> Path:
    Image.fromarray(arr.astype(np.uint8), mode="L").save(path)
    return path


# --- pure estimator ------------------------------------------------------


def test_estimate_staff_space_recovers_known_spacing():
    img = _five_line_staff(spacing=10)
    est = estimate_staff_space(img)
    # The synthesised image has perfect 10 px spacing — recovery should be
    # exact, with full confidence.
    assert est.staff_space_px == 10.0
    assert est.line_count_estimate == 5
    assert est.confidence == 1.0


def test_estimate_handles_blank_image():
    img = np.full((50, 50), 255.0, dtype=np.float32)
    est = estimate_staff_space(img)
    assert est.staff_space_px == 0.0
    assert est.confidence == 0.0


def test_estimate_handles_empty_image():
    img = np.zeros((0, 0), dtype=np.float32)
    est = estimate_staff_space(img)
    assert est.staff_space_px == 0.0
    assert est.line_count_estimate == 0


# --- gate ----------------------------------------------------------------


def test_quality_gate_passes_when_above_thresholds():
    est = estimate_staff_space(_five_line_staff(spacing=12))
    passed, reasons = quality_gate_pass(est, min_confidence=0.9, min_line_count=5)
    assert passed is True
    assert reasons == []


def test_quality_gate_collects_all_reasons():
    # Force a degenerate estimate.
    from app.pipeline.stages.preprocess import StaffSpaceEstimate
    est = StaffSpaceEstimate(staff_space_px=5.0, line_count_estimate=2, confidence=0.4)
    passed, reasons = quality_gate_pass(est, min_confidence=0.85, min_line_count=5)
    assert passed is False
    # Both failures listed so triage can see them at once.
    assert any("line_count" in r for r in reasons)
    assert any("confidence" in r for r in reasons)


# --- stage integration ---------------------------------------------------


def _stage_input(tmp_path, params, image_array=None):
    store = FileArtifactStore(root=tmp_path / "art", job_id="j1")
    if image_array is not None:
        png = _save_png(image_array, tmp_path / "img.png")
        store.put(ArtifactRef(kind="input_image", path=str(png)))
    return StageInput(
        job_id="j1", image_id="page_0", params=params, artifacts=store, trace={}
    )


def test_stage_skipped_when_disabled(tmp_path):
    out = staff_norm_stage(
        _stage_input(tmp_path, params={"preprocess": {"staff_norm": {"enabled": False}}})
    )
    assert out.status == "skipped"
    assert out.metrics.fields == {"preprocess.staff_norm.enabled": False}


def test_stage_ok_with_clean_image(tmp_path):
    params = {
        "preprocess": {
            "staff_norm": {"enabled": True, "target_staff_space_px": 22, "tolerance_px": 3},
            "quality_gate": {"enabled": True, "min_staff_detection_rate": 0.8, "min_line_count": 5, "on_fail": "drop"},
        }
    }
    out = staff_norm_stage(
        _stage_input(tmp_path, params=params, image_array=_five_line_staff(spacing=12))
    )
    assert out.status == "ok"
    assert out.metrics.fields["preprocess.staff_norm.staff_space_px"] == 12.0
    assert out.metrics.fields["preprocess.quality_gate.passed"] is True


def test_stage_drops_low_quality_input(tmp_path):
    params = {
        "preprocess": {
            "staff_norm": {"enabled": True, "target_staff_space_px": 22, "tolerance_px": 3},
            "quality_gate": {"enabled": True, "min_staff_detection_rate": 0.99, "min_line_count": 5, "on_fail": "drop"},
        }
    }
    # Blank image -> confidence 0 -> gate fails.
    out = staff_norm_stage(
        _stage_input(tmp_path, params=params, image_array=np.full((50, 50), 255, dtype=np.float32))
    )
    assert out.status == "skipped"
    assert out.metrics.fields["preprocess.quality_gate.passed"] is False
    assert "failure_reason" in [k.split(".")[-1] for k in out.metrics.fields.keys()]


def test_stage_retryable_when_on_fail_retry_alt_params(tmp_path):
    params = {
        "preprocess": {
            "staff_norm": {"enabled": True, "target_staff_space_px": 22, "tolerance_px": 3},
            "quality_gate": {"enabled": True, "min_staff_detection_rate": 0.99, "min_line_count": 5, "on_fail": "retry_alt_params"},
        }
    }
    out = staff_norm_stage(
        _stage_input(tmp_path, params=params, image_array=np.full((50, 50), 255, dtype=np.float32))
    )
    assert out.status == "retryable"


def test_stage_failed_when_no_image(tmp_path):
    params = {"preprocess": {"staff_norm": {"enabled": True, "target_staff_space_px": 22, "tolerance_px": 3},
                              "quality_gate": {"enabled": False, "min_staff_detection_rate": 0.8, "min_line_count": 5, "on_fail": "drop"}}}
    out = staff_norm_stage(_stage_input(tmp_path, params=params))
    assert out.status == "failed"
    assert "input_image" in (out.error or "")


def test_stage_registered_under_canonical_name():
    from app.pipeline.registry import default_registry
    # Resolution must succeed — if it fails, the import-time registration
    # in stages/__init__.py regressed.
    fn = default_registry.resolve("preprocess.staff_norm")
    assert fn is staff_norm_stage
