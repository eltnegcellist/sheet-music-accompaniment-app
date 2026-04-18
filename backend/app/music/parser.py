"""MusicXML helpers used by the FastAPI layer.

We deliberately keep the dependency surface small (just lxml) and only extract
what the playback engine needs: divisions, an initial tempo, and the list of
measures that should be highlightable.
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from ..omr.audiveris_runner import OmrResult


@dataclass
class MeasureRef:
    index: int
    page: int
    bbox: tuple[float, float, float, float]


def _parse(xml: str) -> etree._Element:
    return etree.fromstring(xml.encode("utf-8"))


def extract_divisions_and_tempo(music_xml: str) -> tuple[int, float]:
    """Return (divisions, tempo_bpm) defaulting to (480, 120) when missing.

    `divisions` is the number of MusicXML duration ticks per quarter note.
    Tempo is taken from the first <sound tempo="..."/> we can find.
    """
    root = _parse(music_xml)

    divisions = 480
    div_el = root.find(".//attributes/divisions")
    if div_el is not None and div_el.text:
        try:
            divisions = int(div_el.text)
        except ValueError:
            pass

    tempo = 120.0
    sound_el = root.find(".//sound[@tempo]")
    if sound_el is not None:
        try:
            tempo = float(sound_el.get("tempo") or tempo)
        except ValueError:
            pass

    return divisions, tempo


def list_measures_with_bbox(
    omr_result: OmrResult,
    accompaniment_part_id: str | None,  # noqa: ARG001 - reserved for future use
) -> list[MeasureRef]:
    """Project Audiveris measure layouts into the playback timeline.

    For now we surface every measure Audiveris detected; per-part filtering
    happens client-side based on `accompaniment_part_id`. We keep the parameter
    on the signature so we can refine this later (e.g. only return measures
    that contain notes for the accompaniment part).
    """
    return [
        MeasureRef(index=m.index, page=m.page, bbox=m.bbox)
        for m in omr_result.measures
    ]
