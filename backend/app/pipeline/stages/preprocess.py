"""Preprocess stage — staff-space normalisation + quality gate (S1-04).

This first cut is intentionally minimal: it operates on already-rendered
grayscale arrays and only depends on numpy + Pillow. Heavier image ops
(Hough deskew, Sauvola binarisation, page curvature correction) are
deferred to a follow-up ticket once we agree on the OpenCV/skimage
budget for the runtime image.

Stages exposed:
  * `preprocess.staff_norm` — measures the staff space, scales toward a
    target staff height, and feeds a quality gate that decides whether
    the image is fit for OMR.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

from ..contracts import (
    ArtifactRef,
    StageInput,
    StageMetrics,
    StageOutput,
)
from ..registry import register


@dataclass
class StaffSpaceEstimate:
    """Estimated staff geometry for one image.

    `confidence` is a heuristic in [0, 1] — closer to 1 when the projection
    has well-separated peaks at the expected line spacing.
    """

    staff_space_px: float
    line_count_estimate: int
    confidence: float


def _load_grayscale(path: Path) -> np.ndarray:
    """Load an image and reduce it to a 2D grayscale numpy array.

    PIL handles PNG/JPEG/TIFF transparently; we convert to L (8-bit gray)
    so the projection logic only has one shape to worry about.
    """
    img = Image.open(path).convert("L")
    return np.asarray(img, dtype=np.float32)


def _row_darkness(image: np.ndarray) -> np.ndarray:
    """Return a per-row "darkness" projection (255 - mean intensity).

    Darker rows (i.e. those crossing many staff lines) have higher values.
    The simple mean is enough at this scope; a binarised projection would
    be sharper but pulls in more dependencies.
    """
    return 255.0 - image.mean(axis=1)


def _peak_indices(values: np.ndarray, min_separation: int) -> list[int]:
    """Greedy local-maxima picker spaced by `min_separation`.

    We avoid scipy.signal.find_peaks because numpy alone is enough at this
    fidelity and we don't want to pull in scipy just for staff lines.
    """
    if values.size == 0:
        return []
    threshold = float(values.mean() + 0.5 * values.std())
    candidates = np.where(values > threshold)[0]
    picked: list[int] = []
    for idx in candidates:
        if not picked or idx - picked[-1] >= min_separation:
            picked.append(int(idx))
    return picked


def estimate_staff_space(image: np.ndarray) -> StaffSpaceEstimate:
    """Estimate staff line spacing from the row-darkness projection."""
    if image.ndim != 2 or image.size == 0:
        return StaffSpaceEstimate(0.0, 0, 0.0)

    proj = _row_darkness(image)
    # Min separation = 4 px is a conservative lower bound for any printed
    # score we care about; it just stops the same dark band being picked twice.
    peaks = _peak_indices(proj, min_separation=4)

    if len(peaks) < 2:
        return StaffSpaceEstimate(0.0, len(peaks), 0.0)

    diffs = np.diff(peaks)
    median_gap = float(np.median(diffs))
    # Confidence = how tight the gaps cluster around the median.
    if median_gap == 0:
        return StaffSpaceEstimate(0.0, len(peaks), 0.0)
    deviation = float(np.std(diffs) / median_gap)
    confidence = float(max(0.0, min(1.0, 1.0 - deviation)))

    return StaffSpaceEstimate(
        staff_space_px=median_gap,
        line_count_estimate=len(peaks),
        confidence=confidence,
    )


def quality_gate_pass(
    estimate: StaffSpaceEstimate,
    *,
    min_confidence: float,
    min_line_count: int,
) -> tuple[bool, list[str]]:
    """Decide whether the estimate clears the quality gate.

    Returns `(passed, reasons)` so the stage can put the failure reasons
    into warnings / metrics for triage.
    """
    reasons: list[str] = []
    if estimate.line_count_estimate < min_line_count:
        reasons.append(
            f"line_count={estimate.line_count_estimate} < {min_line_count}"
        )
    if estimate.confidence < min_confidence:
        reasons.append(
            f"confidence={estimate.confidence:.2f} < {min_confidence:.2f}"
        )
    return (not reasons, reasons)


@register("preprocess.staff_norm")
def staff_norm_stage(inp: StageInput) -> StageOutput:
    """Pipeline stage: estimate staff geometry + quality-gate the input image.

    Inputs:
      * Artifact `input_image` (PNG/JPEG/TIFF). When unavailable, falls
        back to `params.preprocess.input_image` for tests/replays.
      * `params.preprocess.staff_norm.{enabled,target_staff_space_px,...}`
      * `params.preprocess.quality_gate.{enabled,min_*}`

    Outputs:
      * `metrics.fields["preprocess.staff_norm.*"]` — staff_space_px,
        line_count, confidence, gate_passed
      * `status="skipped"` when the gate fails with `on_fail=drop`
      * `status="retryable"` when the gate fails with `on_fail=retry_alt_params`
    """
    pp = inp.params.get("preprocess", {})
    cfg = pp.get("staff_norm", {})
    if not cfg.get("enabled", False):
        return StageOutput(
            status="skipped",
            metrics=StageMetrics(fields={"preprocess.staff_norm.enabled": False}),
        )

    image_path = _resolve_image_path(inp)
    if image_path is None:
        return StageOutput(
            status="failed",
            error="preprocess.staff_norm: no input_image artifact and no params.preprocess.input_image",
        )

    image = _load_grayscale(image_path)
    est = estimate_staff_space(image)

    gate_cfg = pp.get("quality_gate", {})
    gate_enabled = gate_cfg.get("enabled", False)
    on_fail = gate_cfg.get("on_fail", "drop")
    min_conf = gate_cfg.get("min_staff_detection_rate", 0.85)
    min_lines = gate_cfg.get("min_line_count", 5)

    metrics = StageMetrics(
        fields={
            "preprocess.staff_norm.enabled": True,
            "preprocess.staff_norm.staff_space_px": round(est.staff_space_px, 3),
            "preprocess.staff_norm.line_count_estimate": est.line_count_estimate,
            "preprocess.staff_norm.confidence": round(est.confidence, 3),
        }
    )

    if not gate_enabled:
        return StageOutput(status="ok", metrics=metrics)

    passed, reasons = quality_gate_pass(
        est, min_confidence=min_conf, min_line_count=min_lines
    )
    metrics.fields["preprocess.quality_gate.passed"] = passed
    if passed:
        return StageOutput(status="ok", metrics=metrics)

    metrics.fields["preprocess.quality_gate.failure_reason"] = "; ".join(reasons)
    if on_fail == "retry_alt_params":
        return StageOutput(
            status="retryable",
            metrics=metrics,
            warnings=[f"quality gate failed: {r}" for r in reasons],
            error="quality gate failed",
        )
    return StageOutput(
        status="skipped",
        metrics=metrics,
        warnings=[f"quality gate failed: {r}" for r in reasons],
    )


def _resolve_image_path(inp: StageInput) -> Path | None:
    ref = inp.artifacts.get("input_image")
    if ref is not None:
        return Path(ref.path)
    explicit = inp.params.get("preprocess", {}).get("input_image")
    return Path(explicit) if explicit else None
