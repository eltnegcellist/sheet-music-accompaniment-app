"""End-to-end measurement against real PDFs (S3-04-a).

This test runs Audiveris on user-supplied PDFs and compares the pipeline
output across param-set versions (v1 baseline … v5 with all fixes).
Audiveris is slow (10–60 minutes per PDF) so:

  * The test is **opt-in only** via `RUN_REAL_PDF_E2E=1` — pytest's
    default invocation skips it.
  * Audiveris output is **cached** under
    `tests/fixtures/real_pdf/.cache/<sha256>.musicxml` so subsequent
    runs reuse it.
  * Setting `RUN_REAL_PDF_E2E=cached` skips the Audiveris invocation
    entirely and only re-runs the pipeline on cached output, which is
    what the user normally wants when iterating on postprocess code.

How to use (from docker-compose with Audiveris available):
    RUN_REAL_PDF_E2E=1 pytest tests/pipeline/test_real_pdf_e2e.py -s

Drop your PDFs in `tests/fixtures/real_pdf/` first (the directory is
gitignored). The test prints a per-PDF lift table to stdout so you can
see at a glance whether v5 actually helps on your inputs.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pytest

from app.omr.audiveris_runner import run_audiveris
from app.pipeline.params_loader import load_params
from app.pipeline.full_run import run_postprocess_and_evaluate
from app.pipeline.scoring_facade import evaluate_musicxml_metrics


REAL_PDF_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "real_pdf"
CACHE_DIR = REAL_PDF_DIR / ".cache"
PARAMS_DIR = Path(__file__).resolve().parents[2] / "params"
SCHEMA = PARAMS_DIR / "schema.json"

# Param sets to compare. Keep ordered from least → most aggressive so the
# printed table reads as a progression.
PARAM_SETS = (
    "v1_baseline",
    "v3_with_postprocess",
    "v4_with_pitch",
    "v5_real_pdf",
)


@dataclass
class FixtureResult:
    pdf_name: str
    omr_xml_bytes: int
    scores_by_paramset: dict[str, float]
    edits_by_paramset: dict[str, int]


def _enabled_mode() -> str:
    """Return 'audiveris', 'cached', or '' (disabled)."""
    flag = os.environ.get("RUN_REAL_PDF_E2E", "").strip().lower()
    if flag in ("1", "true", "audiveris"):
        return "audiveris"
    if flag == "cached":
        return "cached"
    return ""


def _audiveris_available() -> bool:
    return shutil.which("Audiveris") is not None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_cache_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def _cache_path_for(pdf: Path) -> Path:
    return _ensure_cache_dir() / f"{_sha256(pdf)}.musicxml"


def _get_or_run_audiveris(pdf: Path, mode: str) -> str | None:
    """Return the Audiveris MusicXML output for `pdf`.

    `mode` decides whether we may shell out to Audiveris (`'audiveris'`)
    or only consult the cache (`'cached'`). Returns None when cached
    output is unavailable in cache-only mode.
    """
    cache = _cache_path_for(pdf)
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    if mode == "cached":
        return None

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        result = run_audiveris(pdf, out_dir)
        if not result.music_xml:
            return None
        cache.write_text(result.music_xml, encoding="utf-8")
        return result.music_xml


def _score_under(xml: str, param_set_id: str) -> tuple[float, int]:
    """Return (final_score, edits_count) for the given xml + param set."""
    params = load_params(param_set_id, PARAMS_DIR, schema_path=SCHEMA).data
    pp = params.get("postprocess", {})
    rhythm_cfg = pp.get("rhythm_fix") or {}
    run = run_postprocess_and_evaluate(
        xml,
        fill_measures_enabled=bool((pp.get("fill_measures") or {}).get("enabled")),
        fix_key_accidentals_enabled=bool(
            (pp.get("fix_key_accidentals") or {}).get("enabled")
        ),
        rhythm_fix_enabled=bool((pp.get("rhythm_fix") or {}).get("enabled")),
        voice_rebuild_enabled=bool((pp.get("voice_rebuild") or {}).get("enabled")),
        pitch_fix_enabled=bool((pp.get("pitch_fix") or {}).get("enabled")),
        snap_durations=list(rhythm_cfg.get("snap_durations") or [1, 2, 4, 8, 16]),
        max_edits_per_measure=int(rhythm_cfg.get("max_edits_per_measure", 4)),
    )
    if run is None:
        # Fall back to raw score so the table still prints something useful.
        raw = evaluate_musicxml_metrics(xml)
        return float(raw["final_score"]) if raw else 0.0, 0
    return run.final_score, run.edits_count


def _format_table(results: Iterable[FixtureResult]) -> str:
    results = list(results)
    if not results:
        return "(no results)"
    header = f"{'pdf':40s} " + " ".join(f"{ps[:14]:>14s}" for ps in PARAM_SETS)
    lines = [header, "-" * len(header)]
    for r in results:
        cells = " ".join(
            f"{r.scores_by_paramset[ps]:>14.4f}" for ps in PARAM_SETS
        )
        lines.append(f"{r.pdf_name[:40]:40s} {cells}")
    # Average row
    avg = " ".join(
        f"{sum(r.scores_by_paramset[ps] for r in results) / len(results):>14.4f}"
        for ps in PARAM_SETS
    )
    lines.append("-" * len(header))
    lines.append(f"{'AVERAGE':40s} {avg}")
    return "\n".join(lines)


def test_real_pdf_lift_under_each_paramset(capfd):
    mode = _enabled_mode()
    if not mode:
        pytest.skip(
            "Set RUN_REAL_PDF_E2E=1 to drive Audiveris, or "
            "RUN_REAL_PDF_E2E=cached to score cached output only."
        )
    REAL_PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(REAL_PDF_DIR.glob("*.pdf"))
    if not pdfs:
        pytest.skip(
            f"No PDFs found under {REAL_PDF_DIR}. "
            "Drop one or more *.pdf files into that directory and re-run."
        )
    if mode == "audiveris" and not _audiveris_available():
        pytest.skip(
            "Audiveris not on PATH; install it or rerun with "
            "RUN_REAL_PDF_E2E=cached after caching."
        )

    results: list[FixtureResult] = []
    for pdf in pdfs:
        xml = _get_or_run_audiveris(pdf, mode=mode)
        if xml is None:
            # cache-only mode without prior run; record as N/A but skip
            print(f"[skip] {pdf.name}: no cached Audiveris output yet")
            continue
        scores: dict[str, float] = {}
        edits: dict[str, int] = {}
        for ps in PARAM_SETS:
            s, e = _score_under(xml, ps)
            scores[ps] = s
            edits[ps] = e
        results.append(
            FixtureResult(
                pdf_name=pdf.name,
                omr_xml_bytes=len(xml),
                scores_by_paramset=scores,
                edits_by_paramset=edits,
            )
        )

    if not results:
        pytest.skip("No usable Audiveris output (cached or fresh) for any PDF.")

    # Print so the user can see the lift even when the assertion passes.
    print("\n=== Real-PDF pipeline lift ===")
    print(_format_table(results))

    # Soft assertion: v5 average must not regress vs v1. We deliberately
    # don't enforce a positive lift here because real PDFs vary widely;
    # the table is the actual signal.
    avg_v1 = sum(r.scores_by_paramset["v1_baseline"] for r in results) / len(results)
    avg_v5 = sum(r.scores_by_paramset["v5_real_pdf"] for r in results) / len(results)
    assert avg_v5 >= avg_v1 - 0.005, (
        f"v5 average final_score regressed vs v1 on real PDFs: "
        f"v1={avg_v1:.4f} v5={avg_v5:.4f}"
    )
