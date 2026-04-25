"""Re-compute the golden baseline JSON from the current fixture set.

Run from `backend/`:
    python scripts/refresh_golden_baseline.py

The output is committed alongside an explicit `fixtures: refresh baseline`
message so reviewers can spot accidental shifts in metric definitions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `import app.*` when running from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline.scoring_facade import evaluate_musicxml_metrics  # noqa: E402

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "golden"
BASELINE = GOLDEN_DIR / "baseline.json"


def main() -> int:
    samples: dict[str, dict] = {}
    for fixture in sorted(GOLDEN_DIR.glob("*.musicxml")):
        xml = fixture.read_text(encoding="utf-8")
        metrics = evaluate_musicxml_metrics(xml)
        if metrics is None:
            print(f"!! Could not score {fixture.name}", file=sys.stderr)
            return 1
        samples[fixture.name] = metrics

    payload = {
        "_doc": (
            "Baseline metrics for the regression test. To refresh, run "
            "scripts/refresh_golden_baseline.py and commit the diff with "
            "message 'fixtures: refresh baseline'. Never edit by hand."
        ),
        "_version": 1,
        "samples": samples,
    }
    BASELINE.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {BASELINE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
