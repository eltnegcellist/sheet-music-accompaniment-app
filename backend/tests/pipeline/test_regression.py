"""Phase 4-4 regression test: golden samples must not score lower.

The plan calls out two CI assertions:
  * average final_score across all samples must not regress
  * 95th percentile of measure_duration_match must stay above its baseline

Tolerance is small but non-zero so trivial floating-point reordering
(e.g. iteration-order changes in music21) doesn't trip the test. To
intentionally update a baseline run scripts/refresh_golden_baseline.py
and commit with `fixtures: refresh baseline`.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

import pytest

from app.pipeline.scoring_facade import evaluate_musicxml_metrics


GOLDEN_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "golden"
BASELINE = GOLDEN_DIR / "baseline.json"

# Per-sample tolerance — 0.5 percentage points absolute. Generous enough
# for music21 minor-version drift, tight enough to catch real regressions.
TOLERANCE = 0.005


def _load_baseline() -> dict[str, dict[str, float]]:
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    return payload["samples"]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
    return s[idx]


@pytest.fixture(scope="module")
def computed_metrics() -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for fixture in sorted(GOLDEN_DIR.glob("*.musicxml")):
        metrics = evaluate_musicxml_metrics(fixture.read_text(encoding="utf-8"))
        assert metrics is not None, f"failed to score {fixture.name}"
        out[fixture.name] = metrics
    return out


def test_baseline_covers_every_fixture(computed_metrics):
    baseline = _load_baseline()
    fixtures = set(computed_metrics)
    baselined = set(baseline)
    missing = fixtures - baselined
    extra = baselined - fixtures
    assert not missing, (
        f"baseline.json missing entries for {sorted(missing)}; "
        "run scripts/refresh_golden_baseline.py"
    )
    assert not extra, (
        f"baseline.json has stale entries {sorted(extra)} for deleted fixtures"
    )


def test_per_sample_metrics_within_tolerance(computed_metrics):
    """Each sample's individual sub-scores must not drift beyond TOLERANCE."""
    baseline = _load_baseline()
    failures: list[str] = []
    for name, expected in baseline.items():
        actual = computed_metrics[name]
        for key, exp in expected.items():
            got = actual[key]
            if abs(got - exp) > TOLERANCE:
                failures.append(
                    f"{name} {key}: baseline={exp} actual={got} "
                    f"(diff={got - exp:+.4f}, tolerance={TOLERANCE})"
                )
    assert not failures, "\n".join(failures)


def test_average_final_score_does_not_regress(computed_metrics):
    """Phase 4-4 KPI: mean final_score across the golden set must not drop."""
    baseline = _load_baseline()
    base_avg = mean(s["final_score"] for s in baseline.values())
    cur_avg = mean(s["final_score"] for s in computed_metrics.values())
    assert cur_avg >= base_avg - TOLERANCE, (
        f"average final_score regressed: was {base_avg:.4f}, now {cur_avg:.4f}"
    )


def test_p95_measure_duration_match_holds(computed_metrics):
    """95th percentile of measure_duration_match must stay above baseline.

    Phase 4-4 explicitly calls this out — degraded rhythm fix shows up
    here before it shows up in the average.
    """
    baseline = _load_baseline()
    base_p95 = _percentile(
        [s["measure_duration_match"] for s in baseline.values()], 0.95
    )
    cur_p95 = _percentile(
        [s["measure_duration_match"] for s in computed_metrics.values()], 0.95
    )
    assert cur_p95 >= base_p95 - TOLERANCE, (
        f"p95 measure_duration_match regressed: was {base_p95}, now {cur_p95}"
    )


def test_golden_set_has_at_least_five_samples():
    # The plan asks for ~20 samples eventually; keep CI gating at the
    # number actually shipped so accidental deletions are caught.
    fixtures = list(GOLDEN_DIR.glob("*.musicxml"))
    assert len(fixtures) >= 5, "Sprint 2 DoD requires ≥ 5 golden fixtures"
