from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree
from music21 import chord, converter, note, stream

logger = logging.getLogger(__name__)


@dataclass
class NoteEvent:
    measure_no: int
    voice: str
    onset_q: float
    dur_q: float
    midi: int | None
    is_rest: bool


def _extract_events_from_measure(measure: stream.Measure) -> list[NoteEvent]:
    events: list[NoteEvent] = []
    m_no = int(measure.number) if measure.number is not None else -1
    for n in measure.notesAndRests:
        onset = float(n.offset)
        dur = float(n.quarterLength)
        voice_obj = getattr(n, "voice", None)
        voice = str(voice_obj.id) if voice_obj is not None and voice_obj.id else "1"

        if n.isRest:
            events.append(
                NoteEvent(m_no, voice, onset, dur, None, True)
            )
        elif isinstance(n, chord.Chord):
            for pitch in n.pitches:
                events.append(
                    NoteEvent(m_no, voice, onset, dur, int(pitch.midi), False)
                )
        elif isinstance(n, note.Note):
            events.append(
                NoteEvent(m_no, voice, onset, dur, int(n.pitch.midi), False)
            )
    return events


def _measure_score(events: list[NoteEvent], expected_q: float = 4.0) -> float:
    score = 100.0

    by_voice: dict[str, float] = {}
    for e in events:
        by_voice[e.voice] = by_voice.get(e.voice, 0.0) + e.dur_q

    for total in by_voice.values():
        score -= abs(total - expected_q) * 12.0

    notes = sorted([e for e in events if not e.is_rest], key=lambda x: x.onset_q)
    jumps = 0
    for i in range(1, len(notes)):
        prev = notes[i - 1]
        curr = notes[i]
        if prev.midi is not None and curr.midi is not None:
            if abs(curr.midi - prev.midi) > 19:
                jumps += 1
    score -= jumps * 2.5

    return score


def _expected_quarter_length(measure: stream.Measure) -> float:
    ts = measure.timeSignature
    if ts is None:
        return 4.0
    return float(ts.numerator) * (4.0 / float(ts.denominator))


def _parse_score(xml_text: str) -> stream.Score:
    with tempfile.NamedTemporaryFile(suffix=".musicxml", delete=False) as tmp:
        path = Path(tmp.name)
        path.write_text(xml_text, encoding="utf-8")
    try:
        return converter.parse(str(path))
    finally:
        path.unlink(missing_ok=True)


def fuse_omr_results(audiveris_xml: str, oemer_xml: str | None) -> tuple[str, int]:
    """Fuse Audiveris/Oemer output at measure granularity.

    Returns (musicxml, replaced_measure_count).
    """
    if not oemer_xml:
        return audiveris_xml, 0

    try:
        aud_score = _parse_score(audiveris_xml)
        oem_score = _parse_score(oemer_xml)
        aud_root = etree.fromstring(audiveris_xml.encode("utf-8"))
        oem_root = etree.fromstring(oemer_xml.encode("utf-8"))
    except Exception:
        logger.exception("Failed to parse OMR XML for fusion")
        return audiveris_xml, 0

    replaced = 0

    aud_parts = aud_score.parts
    oem_parts = oem_score.parts
    for part_idx, aud_part in enumerate(aud_parts):
        if part_idx >= len(oem_parts):
            break
        oem_part = oem_parts[part_idx]

        part_id = aud_part.id if aud_part.id else f"P{part_idx + 1}"
        xml_aud_part = aud_root.find(f".//part[@id='{part_id}']")
        xml_oem_part = oem_root.find(f".//part[@id='{oem_part.id}']") if oem_part.id else None
        if xml_oem_part is None:
            xml_oem_part = oem_root.find(f".//part[@id='P{part_idx + 1}']")
        if xml_aud_part is None or xml_oem_part is None:
            continue

        aud_measures = list(aud_part.getElementsByClass("Measure"))
        for aud_measure in aud_measures:
            if aud_measure.number is None:
                continue
            m_no = int(aud_measure.number)
            oem_measure = oem_part.measure(m_no)
            if oem_measure is None:
                continue

            expected_q = _expected_quarter_length(aud_measure)
            score_a = _measure_score(_extract_events_from_measure(aud_measure), expected_q)
            score_b = _measure_score(_extract_events_from_measure(oem_measure), expected_q)
            if score_b <= score_a + 5.0:
                continue

            xml_aud_measure = xml_aud_part.find(f"./measure[@number='{m_no}']")
            xml_oem_measure = xml_oem_part.find(f"./measure[@number='{m_no}']")
            if xml_aud_measure is None or xml_oem_measure is None:
                continue

            for child in list(xml_aud_measure):
                if child.tag == "attributes":
                    continue
                xml_aud_measure.remove(child)
            for child in list(xml_oem_measure):
                if child.tag == "attributes":
                    continue
                xml_aud_measure.append(etree.fromstring(etree.tostring(child)))
            replaced += 1

    return etree.tostring(aud_root, encoding="unicode"), replaced
