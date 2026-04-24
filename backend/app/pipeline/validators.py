"""MusicXML shape validators.

Phase 2-4-a: detect "broken" Audiveris output before it propagates into
the rest of the pipeline. The checks here are intentionally cheap and
independent of music21 — they catch the failure modes we observe in
production (zero measures, zero notes, all-empty parts, malformed XML).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from lxml import etree


@dataclass
class XmlIssue:
    """A single problem found in a MusicXML document.

    `code` is a stable token used for log aggregation; `detail` is human text.
    """

    code: str
    detail: str


@dataclass
class ValidationReport:
    issues: list[XmlIssue] = field(default_factory=list)
    measure_count: int = 0
    note_count: int = 0
    avg_notes_per_measure: float = 0.0
    part_count: int = 0
    empty_parts: int = 0

    @property
    def is_broken(self) -> bool:
        return bool(self.issues)


def _iter_notes(part: etree._Element) -> Iterable[etree._Element]:
    return part.iter("note")


def validate_musicxml_shape(
    xml: str,
    *,
    max_avg_notes_per_measure: float = 50.0,
) -> ValidationReport:
    """Inspect a MusicXML string for the shape failures listed in Phase 2-4.

    The function never raises on bad XML — it records `xml_parse_error`
    in the report so the caller can decide policy (fail vs retry).
    """
    report = ValidationReport()

    if not xml or not xml.strip():
        report.issues.append(XmlIssue("empty_input", "MusicXML payload is empty"))
        return report

    try:
        root = etree.fromstring(xml.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        report.issues.append(XmlIssue("xml_parse_error", str(exc)))
        return report

    tag = etree.QName(root).localname
    if tag not in {"score-partwise", "score-timewise"}:
        report.issues.append(
            XmlIssue("bad_root", f"Root element is <{tag}>; expected score-(part|time)wise")
        )
        return report

    parts = root.findall(".//part")
    report.part_count = len(parts)
    if report.part_count == 0:
        report.issues.append(XmlIssue("no_parts", "Document contains no <part>"))
        return report

    measures = root.findall(".//measure")
    report.measure_count = len(measures)
    if report.measure_count == 0:
        report.issues.append(XmlIssue("zero_measures", "No <measure> elements"))

    total_notes = 0
    empty_parts = 0
    for part in parts:
        notes_in_part = sum(1 for _ in _iter_notes(part))
        total_notes += notes_in_part
        rests_in_part = sum(1 for _ in part.iter("rest"))
        if notes_in_part == 0 and rests_in_part == 0:
            empty_parts += 1

    report.note_count = total_notes
    report.empty_parts = empty_parts
    if report.measure_count > 0:
        report.avg_notes_per_measure = total_notes / report.measure_count

    if total_notes == 0:
        report.issues.append(XmlIssue("zero_notes", "No <note> elements in any part"))
    if empty_parts == report.part_count:
        report.issues.append(
            XmlIssue("all_parts_empty", "Every part is missing notes and rests")
        )
    if (
        report.measure_count > 0
        and report.avg_notes_per_measure > max_avg_notes_per_measure
    ):
        report.issues.append(
            XmlIssue(
                "absurd_density",
                f"Average notes/measure {report.avg_notes_per_measure:.1f} "
                f"exceeds the {max_avg_notes_per_measure} sanity ceiling",
            )
        )

    return report
