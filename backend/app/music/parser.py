"""MusicXML helpers used by the FastAPI layer.

We deliberately keep the dependency surface small (just lxml) and only extract
what the playback engine needs: divisions, an initial tempo, and the list of
measures that should be highlightable.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from lxml import etree

from ..omr.audiveris_runner import OmrResult

logger = logging.getLogger(__name__)


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


@dataclass
class TempoInfo:
    """Result + provenance for the tempo extraction pass.

    `source` tells us which rule fired, which is invaluable for debugging
    scores where the UI ends up with the 120 default even though the
    engraving clearly marks e.g. "Andantino". `candidates` lists the raw
    text strings we scanned, so the user can see at a glance whether
    Audiveris OCR'd the marking at all.
    """

    bpm: float
    source: str  # "sound" | "metronome" | "word" | "default"
    candidates: list[str]


def _parse(xml: str) -> etree._Element:
    return etree.fromstring(xml.encode("utf-8"))


def extract_divisions_and_tempo(music_xml: str) -> tuple[int, float]:
    root = _parse(music_xml)
    return _extract_divisions(root), _extract_tempo_info(root).bpm


def extract_tempo_info(music_xml: str) -> TempoInfo:
    return _extract_tempo_info(_parse(music_xml))


def _extract_divisions(root: etree._Element) -> int:
    div_el = root.find(".//attributes/divisions")
    if div_el is not None and div_el.text:
        try:
            return int(div_el.text)
        except ValueError:
            pass
    return 480


def _extract_tempo_info(root: etree._Element) -> TempoInfo:
    """Resolve tempo and track provenance.

    Priority: <sound tempo=...> > <metronome> > tempo word > 120 default.
    """
    candidates = _collect_tempo_text(root)

    sound_el = root.find(".//sound[@tempo]")
    if sound_el is not None:
        try:
            bpm = float(sound_el.get("tempo") or 0) or 120.0
            logger.info("Tempo from <sound>: %s BPM", bpm)
            return TempoInfo(bpm=bpm, source="sound", candidates=candidates)
        except ValueError:
            pass

    metro = _first_metronome_bpm(root)
    if metro is not None:
        logger.info("Tempo from <metronome>: %s BPM", metro)
        return TempoInfo(bpm=metro, source="metronome", candidates=candidates)

    word_bpm = _first_tempo_word_bpm_from(candidates)
    if word_bpm is not None:
        return TempoInfo(bpm=word_bpm, source="word", candidates=candidates)

    logger.info("No tempo information found; defaulting to 120 BPM")
    return TempoInfo(bpm=120.0, source="default", candidates=candidates)


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


def _collect_tempo_text(root: etree._Element) -> list[str]:
    # Audiveris emits tempo markings inconsistently: sometimes as proper
    # <direction-type><words>Andantino</words></direction-type>, but often as
    # <credit-words> on the title page (especially when the word sits above
    # the first system, where Audiveris treats it as a credit/heading rather
    # than a musical direction). Search both, plus any other stray text
    # elements, so we don't silently miss obvious markings.
    candidate_tags = ("words", "credit-words", "rehearsal")
    collected: list[str] = []
    for tag in candidate_tags:
        for el in root.iter(tag):
            text = (el.text or "").strip()
            if text:
                collected.append(text)
    if collected:
        logger.info("Tempo text candidates found: %r", collected)
    else:
        logger.info("No <words>/<credit-words>/<rehearsal> text in MusicXML")
    return collected


def _first_tempo_word_bpm_from(candidates: list[str]) -> float | None:
    for raw in candidates:
        text = raw.lower()
        text = re.sub(r"[^\w\s]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        for key in _TEMPO_WORDS_SORTED:
            if re.search(rf"\b{re.escape(key)}\b", text):
                logger.info(
                    "Matched tempo word %r in %r -> %s BPM",
                    key,
                    raw,
                    _TEMPO_WORD_BPM[key],
                )
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
