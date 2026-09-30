"""Confidence-gated hybrid OMR.

The hybrid engine runs both Audiveris and homr, keeps Audiveris layout when it
is structurally healthy, falls back to homr when Audiveris clearly collapses,
and only copies homr pitch into Audiveris MusicXML when note correspondence is
safe enough to preserve Audiveris rhythm/voice structure.
"""

from __future__ import annotations

import copy
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from lxml import etree

from ..music.accompaniment import find_accompaniment_part
from .audiveris_runner import run_audiveris_chunked
from .homr_runner import HomrError, run_homr
from .result import OmrError, OmrResult

logger = logging.getLogger(__name__)


def _metrics(xml: str) -> dict[str, float] | None:
    # Import lazily to avoid pulling the pipeline package into engine import
    # time and to keep the OMR adapter usable in lightweight tests.
    from ..pipeline.scoring_facade import evaluate_musicxml_metrics

    return evaluate_musicxml_metrics(xml)


def _part_count(xml: str) -> int:
    root = etree.fromstring(xml.encode("utf-8"))
    return len(root.findall("./part"))


def _part_by_id(root: etree._Element, part_id: str | None) -> etree._Element | None:
    if not part_id:
        return None
    return root.find(f"./part[@id='{part_id}']")


def _pitched_groups(measure: etree._Element) -> dict[tuple[str, str], list[etree._Element]]:
    groups: dict[tuple[str, str], list[etree._Element]] = defaultdict(list)
    for note in measure.findall(".//note"):
        if note.find("pitch") is None:
            continue
        staff = (note.findtext("staff") or "1").strip()
        voice = (note.findtext("voice") or "1").strip()
        groups[(staff, voice)].append(note)
    return groups


def _rhythmic_signature(note: etree._Element) -> tuple[str, bool]:
    return ((note.findtext("duration") or "").strip(), note.find("chord") is not None)


def _copy_pitch(source: etree._Element, target: etree._Element) -> None:
    source_pitch = source.find("pitch")
    target_pitch = target.find("pitch")
    if source_pitch is None or target_pitch is None:
        return
    target_pitch.getparent().replace(target_pitch, copy.deepcopy(source_pitch))

    source_accidental = source.find("accidental")
    target_accidental = target.find("accidental")
    if target_accidental is not None:
        target.remove(target_accidental)
    if source_accidental is not None:
        pitch_index = list(target).index(target.find("pitch"))
        target.insert(pitch_index + 1, copy.deepcopy(source_accidental))


def _safe_pitch_fusion(
    audiveris_xml: str,
    homr_xml: str,
) -> tuple[str | None, int, int, int]:
    """Return Audiveris XML with safely aligned homr pitches.

    Measures are aligned only when the accompaniment parts have the same measure
    count. Within each measure, every staff/voice group must have equal note
    counts *and* an identical duration/chord sequence before any pitch is
    copied. This deliberately prefers leaving Audiveris untouched over a risky
    correspondence.
    """
    try:
        aud_id = find_accompaniment_part(audiveris_xml)
        homr_id = find_accompaniment_part(homr_xml)
        aud_root = etree.fromstring(audiveris_xml.encode("utf-8"))
        homr_root = etree.fromstring(homr_xml.encode("utf-8"))
    except Exception:
        logger.exception("hybrid: accompaniment-part parsing failed")
        return None, 0, 0, 0

    aud_part = _part_by_id(aud_root, aud_id)
    homr_part = _part_by_id(homr_root, homr_id)
    if aud_part is None or homr_part is None:
        return None, 0, 0, 0

    aud_measures = aud_part.findall("measure")
    homr_measures = homr_part.findall("measure")
    if not aud_measures or len(aud_measures) != len(homr_measures):
        return None, 0, 0, 0

    fused_root = copy.deepcopy(aud_root)
    fused_part = _part_by_id(fused_root, aud_id)
    if fused_part is None:
        return None, 0, 0, 0
    fused_measures = fused_part.findall("measure")

    candidate_notes = 0
    fused_notes = 0
    fused_measure_count = 0

    for aud_measure, homr_measure, fused_measure in zip(
        aud_measures, homr_measures, fused_measures
    ):
        aud_groups = _pitched_groups(aud_measure)
        homr_groups = _pitched_groups(homr_measure)
        fused_groups = _pitched_groups(fused_measure)
        candidate_notes += sum(len(v) for v in aud_groups.values())

        if not aud_groups or set(aud_groups) != set(homr_groups):
            continue

        safe = True
        for key in aud_groups:
            aa = aud_groups[key]
            hh = homr_groups[key]
            if len(aa) != len(hh):
                safe = False
                break
            if [_rhythmic_signature(n) for n in aa] != [
                _rhythmic_signature(n) for n in hh
            ]:
                safe = False
                break
        if not safe:
            continue

        copied_here = 0
        for key in aud_groups:
            for source, target in zip(homr_groups[key], fused_groups[key]):
                _copy_pitch(source, target)
                copied_here += 1
        fused_notes += copied_here
        fused_measure_count += 1

    if fused_notes == 0:
        return None, 0, candidate_notes, 0

    return (
        etree.tostring(fused_root, encoding="unicode"),
        fused_notes,
        candidate_notes,
        fused_measure_count,
    )


def run_hybrid(
    pdf_path: Path,
    output_dir: Path,
    *,
    homr_dpi: int = 300,
    homr_timeout_sec: int = 3600,
    homr_coreml_encoder: bool | None = False,
    duration_floor: float = 0.75,
    strong_duration_gain: float = 0.12,
    minimum_score_gain: float = 0.03,
    fragmentation_part_limit: int = 3,
    minimum_safe_pitch_rate: float = 0.50,
    minimum_safe_pitch_notes: int = 8,
) -> OmrResult:
    """Run confidence-gated Audiveris + homr and return one normalized result."""
    output_dir.mkdir(parents=True, exist_ok=True)

    aud_result: OmrResult | None = None
    aud_error: Exception | None = None
    try:
        aud_result = run_audiveris_chunked(pdf_path, output_dir / "audiveris")
    except Exception as exc:  # Audiveris failures vary widely in practice.
        aud_error = exc
        logger.warning("hybrid: Audiveris failed: %s", exc)

    homr_result: OmrResult | None = None
    homr_error: Exception | None = None
    try:
        homr_result = run_homr(
            pdf_path,
            output_dir / "homr",
            dpi=homr_dpi,
            timeout_sec=homr_timeout_sec,
            coreml_encoder=homr_coreml_encoder,
        )
    except Exception as exc:
        homr_error = exc
        logger.warning("hybrid: homr failed: %s", exc)

    if aud_result is None and homr_result is None:
        raise OmrError(
            "Both hybrid engines failed. "
            f"Audiveris: {aud_error}; homr: {homr_error}"
        )

    if aud_result is None and homr_result is not None:
        return OmrResult(
            music_xml=homr_result.music_xml,
            measures=homr_result.measures,
            page_sizes=homr_result.page_sizes,
            warnings=[
                *homr_result.warnings,
                "ハイブリッド判定: Audiverisが失敗したためhomr結果を採用しました。",
            ],
        )

    if homr_result is None and aud_result is not None:
        return OmrResult(
            music_xml=aud_result.music_xml,
            measures=aud_result.measures,
            page_sizes=aud_result.page_sizes,
            warnings=[
                *aud_result.warnings,
                "ハイブリッド判定: homrが失敗したためAudiveris結果を採用しました。",
            ],
        )

    assert aud_result is not None
    assert homr_result is not None

    aud_metrics = _metrics(aud_result.music_xml) or {}
    homr_metrics = _metrics(homr_result.music_xml) or {}
    aud_duration = float(aud_metrics.get("measure_duration_match", 0.0))
    homr_duration = float(homr_metrics.get("measure_duration_match", 0.0))
    aud_score = float(aud_metrics.get("final_score", 0.0))
    homr_score = float(homr_metrics.get("final_score", 0.0))
    aud_parts = _part_count(aud_result.music_xml)
    homr_parts = _part_count(homr_result.music_xml)

    rhythm_collapse = (
        aud_duration < duration_floor
        and homr_duration >= aud_duration + 0.08
        and homr_score >= aud_score + minimum_score_gain
    )
    strong_homr_gain = (
        homr_duration >= aud_duration + strong_duration_gain
        and homr_score >= aud_score + minimum_score_gain
    )
    aud_fragmented = (
        aud_parts > fragmentation_part_limit
        and homr_parts <= 2
        and homr_duration >= aud_duration
        and homr_score >= aud_score - 0.01
    )

    metric_note = (
        f"Audiveris score={aud_score:.4f}, rhythm={aud_duration:.4f}, parts={aud_parts}; "
        f"homr score={homr_score:.4f}, rhythm={homr_duration:.4f}, parts={homr_parts}."
    )

    if rhythm_collapse or strong_homr_gain or aud_fragmented:
        reason = (
            "Audiverisのリズム崩壊"
            if rhythm_collapse
            else "homrの明確なリズム優位"
            if strong_homr_gain
            else "Audiverisのパート断片化"
        )
        return OmrResult(
            music_xml=homr_result.music_xml,
            measures=homr_result.measures,
            page_sizes=homr_result.page_sizes,
            warnings=[
                *homr_result.warnings,
                f"ハイブリッド判定: {reason}を検出したためhomr結果を採用しました。",
                metric_note,
            ],
        )

    fused_xml, fused_notes, candidate_notes, fused_measures = _safe_pitch_fusion(
        aud_result.music_xml,
        homr_result.music_xml,
    )
    safe_rate = fused_notes / candidate_notes if candidate_notes else 0.0
    if (
        fused_xml is not None
        and fused_notes >= minimum_safe_pitch_notes
        and safe_rate >= minimum_safe_pitch_rate
    ):
        return OmrResult(
            music_xml=fused_xml,
            measures=aud_result.measures,
            page_sizes=aud_result.page_sizes,
            warnings=[
                *aud_result.warnings,
                (
                    "ハイブリッド判定: Audiverisの小節・音価・声部構造を維持し、"
                    f"安全に対応できた{fused_measures}小節 / {fused_notes}音 "
                    f"({safe_rate:.1%}) の音高をhomr結果から採用しました。"
                ),
                metric_note,
            ],
        )

    return OmrResult(
        music_xml=aud_result.music_xml,
        measures=aud_result.measures,
        page_sizes=aud_result.page_sizes,
        warnings=[
            *aud_result.warnings,
            (
                "ハイブリッド判定: Audiveris構造を採用しました。"
                f"安全なhomr音高融合率は{safe_rate:.1%}のため置換していません。"
            ),
            metric_note,
        ],
    )
