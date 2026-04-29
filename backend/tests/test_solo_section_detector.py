"""Tests for the MusicXML-based solo-section detector."""

from __future__ import annotations

from dataclasses import dataclass

from app.music.solo_section_detector import (
    find_solo_only_measure_range,
    measure_range_to_page_range,
)


@dataclass
class _FakeLayout:
    """Stand-in for omr.layout_parser.MeasureLayout (only `index`/`page`)."""
    index: int
    page: int


def _make_score(piano_measures: list[bool], solo_measures: list[bool] | None = None) -> str:
    """Build a minimal MusicXML score where each list element drives one
    measure of the corresponding part. ``True`` means "has pitched notes",
    ``False`` means "rest only" (== empty accompaniment for our purposes)."""
    if solo_measures is None:
        solo_measures = [True] * len(piano_measures)
    parts_xml = ""

    def _measure_xml(num: int, has_notes: bool) -> str:
        if has_notes:
            return (
                f'<measure number="{num}">'
                '<note><pitch><step>C</step><octave>4</octave></pitch>'
                '<duration>4</duration></note></measure>'
            )
        return (
            f'<measure number="{num}">'
            '<note><rest/><duration>4</duration></note></measure>'
        )

    solo_xml = "".join(_measure_xml(i + 1, has) for i, has in enumerate(solo_measures))
    piano_xml = "".join(_measure_xml(i + 1, has) for i, has in enumerate(piano_measures))
    parts_xml = (
        f'<part id="P1">{solo_xml}</part>'
        f'<part id="P2">{piano_xml}</part>'
    )
    return (
        '<?xml version="1.0"?>'
        '<score-partwise version="3.1">'
        '<part-list>'
        '<score-part id="P1"><part-name>Violin</part-name></score-part>'
        '<score-part id="P2"><part-name>Piano</part-name></score-part>'
        '</part-list>'
        f'{parts_xml}'
        '</score-partwise>'
    )


def test_returns_none_when_accompaniment_part_id_missing() -> None:
    xml = _make_score([True] * 16)
    assert find_solo_only_measure_range(xml, None) is None


def test_uniformly_filled_accompaniment_returns_none() -> None:
    xml = _make_score([True] * 16)
    assert find_solo_only_measure_range(xml, "P2") is None


def test_long_silent_back_run_detected() -> None:
    # 8 played + 12 rest-only piano measures = solo at the back.
    xml = _make_score([True] * 8 + [False] * 12)
    res = find_solo_only_measure_range(xml, "P2")
    assert res is not None
    assert res.solo_at_front is False
    assert res.start_measure == 9
    assert res.end_measure == 20
    assert res.accompaniment_empty_count == 12


def test_long_silent_front_run_detected() -> None:
    xml = _make_score([False] * 12 + [True] * 8)
    res = find_solo_only_measure_range(xml, "P2")
    assert res is not None
    assert res.solo_at_front is True
    assert res.start_measure == 1
    assert res.end_measure == 12
    assert res.accompaniment_empty_count == 12


def test_short_silent_run_below_threshold_skipped() -> None:
    # Only 3 silent measures at the end — below the 8-measure floor.
    xml = _make_score([True] * 17 + [False] * 3)
    assert find_solo_only_measure_range(xml, "P2") is None


def test_silent_middle_does_not_trigger() -> None:
    # 4 played + 12 silent + 4 played: the silence is in the MIDDLE so the
    # detector intentionally ignores it (most likely a real tacet, not an
    # engraving section).
    xml = _make_score([True] * 4 + [False] * 12 + [True] * 4)
    assert find_solo_only_measure_range(xml, "P2") is None


def test_both_ends_silent_picks_longer_side() -> None:
    # Front 6 silent, back 10 silent — back wins.
    xml = _make_score([False] * 6 + [True] * 8 + [False] * 10)
    res = find_solo_only_measure_range(xml, "P2")
    assert res is not None
    assert res.solo_at_front is False
    assert res.accompaniment_empty_count == 10


def test_min_ratio_threshold_scales_with_score_size() -> None:
    # 100 total measures, only 8 silent at end → < 20% so should NOT trigger
    # even though it satisfies the absolute floor.
    xml = _make_score([True] * 92 + [False] * 8)
    assert find_solo_only_measure_range(xml, "P2") is None


def test_silent_run_meeting_both_thresholds_triggers() -> None:
    # 100 measures, 25 silent at end → >= 8 absolute AND >= 20 (20% ratio).
    xml = _make_score([True] * 75 + [False] * 25)
    res = find_solo_only_measure_range(xml, "P2")
    assert res is not None
    assert res.accompaniment_empty_count == 25


def test_measure_range_to_page_range_basic() -> None:
    layouts = [
        _FakeLayout(index=1, page=0),
        _FakeLayout(index=2, page=0),
        _FakeLayout(index=3, page=1),
        _FakeLayout(index=4, page=1),
        _FakeLayout(index=5, page=2),
        _FakeLayout(index=6, page=2),
    ]
    # Measures 3..5 → pages 1..2 → half-open [1, 3)
    assert measure_range_to_page_range(layouts, 3, 5) == (1, 3)


def test_measure_range_to_page_range_returns_none_for_missing() -> None:
    layouts = [_FakeLayout(index=1, page=0), _FakeLayout(index=2, page=0)]
    assert measure_range_to_page_range(layouts, 50, 60) is None


def test_invalid_xml_returns_none() -> None:
    assert find_solo_only_measure_range("<<not xml", "P2") is None
