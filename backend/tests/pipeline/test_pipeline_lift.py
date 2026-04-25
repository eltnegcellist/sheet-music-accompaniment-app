"""Phase 4-4 lift test: postprocess must improve scores on broken inputs.

This is the test that answers "is the pipeline actually doing anything
useful?". For each fixture we compare:
  * `raw_score`  = score the MusicXML as Audiveris emitted it
  * `pp_score`   = score after rhythm_fix + voice_rebuild

Clean fixtures must NOT regress (no false-positive edits).
Broken fixtures must improve by at least `EXPECTED_LIFT`.

The expected lift per fixture is encoded explicitly so a test failure
points at the specific scenario that stopped working.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline.full_run import run_postprocess_and_evaluate
from app.pipeline.scoring_facade import evaluate_musicxml_metrics


GOLDEN_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "golden"

# fixture_name -> (min_lift, exact_no_change)
# - min_lift > 0: postprocess must raise final_score by at least this much
# - exact_no_change=True: postprocess must NOT change final_score (no false +)
EXPECTATIONS: dict[str, tuple[float, bool]] = {
    "01_clean_4_4_C_major.musicxml": (0.0, True),
    "02_short_measure_one_beat_missing.musicxml": (0.10, False),
    "03_long_measure_one_beat_extra.musicxml": (0.10, False),
    "04_drifted_durations.musicxml": (0.0, True),     # totals already match
    "05_piano_two_staves.musicxml": (0.0, True),
    "06_audiveris_dropped_two_beats.musicxml": (0.08, False),
    "07_audiveris_split_chord.musicxml": (0.25, False),
    "08_audiveris_drift_and_short.musicxml": (0.20, False),
}

# Tolerance for "no change" — music21 round-trip can introduce
# imperceptible numeric noise in metrics.
NO_CHANGE_TOLERANCE = 0.005


def _score_pair(name: str) -> tuple[float, float, int]:
    xml = (GOLDEN_DIR / name).read_text(encoding="utf-8")
    raw = evaluate_musicxml_metrics(xml)
    pp = run_postprocess_and_evaluate(xml)
    assert raw is not None, f"raw scoring failed for {name}"
    assert pp is not None, f"postprocess failed for {name}"
    return raw["final_score"], pp.final_score, pp.edits_count


@pytest.mark.parametrize("fixture", sorted(EXPECTATIONS))
def test_postprocess_lift_per_fixture(fixture):
    raw, pp, edits = _score_pair(fixture)
    min_lift, no_change = EXPECTATIONS[fixture]

    if no_change:
        # Clean inputs must round-trip with no edits and no score drift.
        assert edits == 0, (
            f"{fixture}: clean input but postprocess made {edits} edit(s)"
        )
        assert abs(pp - raw) <= NO_CHANGE_TOLERANCE, (
            f"{fixture}: clean input score drifted by {pp - raw:+.4f}"
        )
        return

    lift = pp - raw
    assert lift >= min_lift, (
        f"{fixture}: lift {lift:+.4f} below minimum {min_lift} "
        f"(raw={raw:.4f}, pp={pp:.4f}, edits={edits})"
    )


def test_overall_average_lift_is_positive():
    """Across the broken-only subset the average lift must be positive.

    Catches the case where one fixture got better but the overall
    intervention is net-neutral or harmful.
    """
    broken = [n for n, (lift, no_chg) in EXPECTATIONS.items() if not no_chg and lift > 0]
    diffs = []
    for name in broken:
        raw, pp, _ = _score_pair(name)
        diffs.append(pp - raw)
    assert diffs, "no broken fixtures in EXPECTATIONS — test config issue"
    avg = sum(diffs) / len(diffs)
    assert avg > 0.05, f"average lift on broken fixtures only {avg:+.4f}"
