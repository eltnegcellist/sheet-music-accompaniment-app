"""MusicXML helpers used by the FastAPI layer.

We deliberately keep the dependency surface small (just lxml) and only extract
what the playback engine needs: divisions, an initial tempo, and the list of
measures that should be highlightable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

from ..omr.audiveris_runner import OmrResult


# Canonical BPM for Italian tempo markings. Values sit mid-range per the usual
# teaching tables (Grove / Randel). Users can still override with the on-screen
# tempo slider; this is just the starting point.
_TEMPO_WORD_BPM: dict[str, float] = {
    "grave": 40,
    "largo": 50,
    "lento": 52,
    "larghetto": 63,
    "adagio": 70,
    "adagietto": 75,
    "andante": 82,
    "andantino": 90,
    "andante moderato": 95,
    "moderato": 114,
    "allegretto": 116,
    "allegro moderato": 118,
    "allegro": 140,
    "vivace": 160,
    "vivacissimo": 172,
    "presto": 184,
    "prestissimo": 200,
}
# Longer keys first so "allegro moderato" wins over "allegro".
_TEMPO_WORDS_SORTED = sorted(_TEMPO_WORD_BPM, key=len, reverse=True)


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
    Tempo is resolved in priority order:
      1. First <sound tempo="..."/> — authoritative numeric value.
      2. First <metronome><beat-unit>...<per-minute>N</per-minute></metronome>
         — numeric notation, normalized to quarter-note BPM.
      3. First textual tempo word (Andantino, Allegro, etc.) mapped to a
         canonical BPM.
    """
    root = _parse(music_xml)

    divisions = 480
    div_el = root.find(".//attributes/divisions")
    if div_el is not None and div_el.text:
        try:
            divisions = int(div_el.text)
        except ValueError:
            pass

    tempo = _extract_tempo(root)
    return divisions, tempo


def _extract_tempo(root: etree._Element) -> float:
    sound_el = root.find(".//sound[@tempo]")
    if sound_el is not None:
        try:
            return float(sound_el.get("tempo") or 0) or 120.0
        except ValueError:
            pass

    metro = _first_metronome_bpm(root)
    if metro is not None:
        return metro

    word = _first_tempo_word_bpm(root)
    if word is not None:
        return word

    return 120.0


# Beat-unit → quarter-note multiplier. Used to normalize metronome marks like
# "half note = 60" to the quarter-note BPM that Tone.js uses.
_BEAT_UNIT_TO_QUARTERS: dict[str, float] = {
    "whole": 4.0,
    "half": 2.0,
    "quarter": 1.0,
    "eighth": 0.5,
    "16th": 0.25,
    "32nd": 0.125,
}


def _first_metronome_bpm(root: etree._Element) -> float | None:
    for metro in root.iter("metronome"):
        beat_unit_el = metro.find("beat-unit")
        per_min_el = metro.find("per-minute")
        if beat_unit_el is None or per_min_el is None:
            continue
        unit = (beat_unit_el.text or "").strip().lower()
        try:
            per_min = float((per_min_el.text or "").strip())
        except ValueError:
            continue
        # A dot after <beat-unit> denotes a dotted note (1.5x duration).
        dotted = metro.find("beat-unit-dot") is not None
        quarters_per_beat = _BEAT_UNIT_TO_QUARTERS.get(unit)
        if quarters_per_beat is None:
            continue
        if dotted:
            quarters_per_beat *= 1.5
        return per_min * quarters_per_beat
    return None


def _first_tempo_word_bpm(root: etree._Element) -> float | None:
    for words_el in root.iter("words"):
        text = (words_el.text or "").strip().lower()
        if not text:
            continue
        # Strip trailing punctuation / decorative characters.
        text = re.sub(r"[^\w\s]+$", "", text).strip()
        for key in _TEMPO_WORDS_SORTED:
            if key in text:
                return _TEMPO_WORD_BPM[key]
    return None


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
