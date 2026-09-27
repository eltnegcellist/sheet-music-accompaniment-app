"""Run Audiveris and neural OMR on the same score corpus."""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

import yaml

from ..pipeline.params_loader import load_params
from ..pipeline.run import run_omr_via_pipeline
from ..pipeline.scoring_facade import evaluate_musicxml_metrics
from .metrics import compare_musicxml

ENGINE_PARAM_SETS = {
    "audiveris": "v5_real_pdf",
    "homr": "v6_homr",
}


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("cases"), list):
        raise ValueError("manifest must contain a top-level cases list")
    cases: list[dict[str, Any]] = []
    for index, item in enumerate(raw["cases"], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"case {index} must be a mapping")
        case_id = str(item.get("id") or f"case-{index:03d}")
        pdf_value = item.get("pdf")
        if not pdf_value:
            raise ValueError(f"{case_id}: pdf is required")
        pdf = (path.parent / str(pdf_value)).resolve()
        reference_value = item.get("reference_musicxml")
        reference = (
            (path.parent / str(reference_value)).resolve()
            if reference_value
            else None
        )
        cases.append({
            "id": case_id,
            "pdf": pdf,
            "reference_musicxml": reference,
            "category": str(item.get("category") or ""),
            "notes": str(item.get("notes") or ""),
        })
    return cases


def _flatten(prefix: str, value: dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    return {f"{prefix}{key}": item for key, item in value.items()}


def run_benchmark(
    manifest: Path,
    *,
    engines: list[str],
    output_dir: Path,
) -> list[dict[str, Any]]:
    cases = _load_manifest(manifest)
    backend_root = Path(__file__).resolve().parents[2]
    params_dir = backend_root / "params"
    schema = params_dir / "schema.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    for case in cases:
        pdf = case["pdf"]
        reference_path = case["reference_musicxml"]
        if not pdf.exists():
            raise FileNotFoundError(f"{case['id']}: PDF not found: {pdf}")
        reference_xml = None
        if reference_path is not None:
            if not reference_path.exists():
                raise FileNotFoundError(
                    f"{case['id']}: reference MusicXML not found: {reference_path}"
                )
            reference_xml = reference_path.read_text(
                encoding="utf-8", errors="replace"
            )

        for engine in engines:
            if engine not in ENGINE_PARAM_SETS:
                raise ValueError(
                    f"Unsupported engine {engine!r}; choose from "
                    + ", ".join(sorted(ENGINE_PARAM_SETS))
                )
            param_name = ENGINE_PARAM_SETS[engine]
            resolved = load_params(param_name, params_dir, schema_path=schema)
            case_out = output_dir / case["id"] / engine
            case_out.mkdir(parents=True, exist_ok=True)
            started = time.perf_counter()
            row: dict[str, Any] = {
                "case_id": case["id"],
                "category": case["category"],
                "engine": engine,
                "param_set": resolved.param_set_id(),
                "status": "ok",
            }
            try:
                result = run_omr_via_pipeline(
                    pdf,
                    case_out / "work",
                    param_set_id=resolved.param_set_id(),
                    params=resolved.data,
                )
                elapsed = time.perf_counter() - started
                xml_path = case_out / "recognized.musicxml"
                xml_path.write_text(result.music_xml, encoding="utf-8")
                row["runtime_sec"] = round(elapsed, 3)
                row["output_musicxml"] = str(xml_path)
                row["warnings"] = " | ".join(result.warnings)
                row.update(_flatten(
                    "intrinsic_", evaluate_musicxml_metrics(result.music_xml)
                ))
                if reference_xml is not None:
                    row.update(_flatten(
                        "reference_",
                        compare_musicxml(result.music_xml, reference_xml),
                    ))
            except Exception as exc:
                row["runtime_sec"] = round(time.perf_counter() - started, 3)
                row["status"] = "error"
                row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)

    (output_dir / "results.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    fieldnames = sorted({key for row in rows for key in row})
    with (output_dir / "results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare OMR engines on the same PDF corpus."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--engines",
        default="audiveris,homr",
        help="comma-separated engines (default: audiveris,homr)",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("benchmark-results")
    )
    args = parser.parse_args()
    engines = [item.strip() for item in args.engines.split(",") if item.strip()]
    rows = run_benchmark(
        args.manifest.resolve(),
        engines=engines,
        output_dir=args.output.resolve(),
    )
    ok = sum(1 for row in rows if row["status"] == "ok")
    failed = len(rows) - ok
    print(f"OMR benchmark complete: {ok} ok, {failed} failed")
    print(f"Results: {args.output.resolve() / 'results.csv'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
