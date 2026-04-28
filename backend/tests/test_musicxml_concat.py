"""Tests for MusicXML chunk concatenation."""

from __future__ import annotations

from lxml import etree

from app.music.musicxml_concat import concat_musicxml


def _score(measures_per_part: list[list[int]]) -> str:
    """Build a minimal MusicXML score for testing.

    `measures_per_part[i][j]` is the measure number assigned to measure j of
    part i. Each measure gets a single rest note so the document is valid.
    """
    parts_attrs = "".join(
        f'<score-part id="P{i + 1}"><part-name>P{i + 1}</part-name></score-part>'
        for i in range(len(measures_per_part))
    )
    parts_xml = ""
    for i, measures in enumerate(measures_per_part):
        measure_xml = "".join(
            f'<measure number="{n}"><note><rest/><duration>4</duration></note></measure>'
            for n in measures
        )
        parts_xml += f'<part id="P{i + 1}">{measure_xml}</part>'
    return (
        '<?xml version="1.0"?>'
        '<score-partwise version="3.1">'
        f'<part-list>{parts_attrs}</part-list>'
        f'{parts_xml}'
        '</score-partwise>'
    )


def _measure_numbers(xml: str) -> dict[str, list[int]]:
    root = etree.fromstring(xml.encode("utf-8"))
    out: dict[str, list[int]] = {}
    for part in root.findall("part"):
        out[part.get("id") or "?"] = [
            int(m.get("number") or 0) for m in part.findall("measure")
        ]
    return out


def test_single_chunk_passthrough() -> None:
    xml = _score([[1, 2, 3]])
    assert concat_musicxml([xml]) == xml


def test_two_chunks_renumber_sequentially() -> None:
    a = _score([[1, 2, 3]])
    b = _score([[1, 2]])
    merged = concat_musicxml([a, b])
    assert _measure_numbers(merged) == {"P1": [1, 2, 3, 4, 5]}


def test_two_chunks_two_parts_align_across_parts() -> None:
    a = _score([[1, 2], [1, 2]])
    b = _score([[1, 2, 3], [1, 2, 3]])
    merged = concat_musicxml([a, b])
    nums = _measure_numbers(merged)
    assert nums["P1"] == [1, 2, 3, 4, 5]
    assert nums["P2"] == [1, 2, 3, 4, 5]


def test_invalid_chunk_skipped_with_warning() -> None:
    a = _score([[1, 2]])
    bad = "<not-musicxml/>but-broken"
    c = _score([[1, 2]])
    warnings: list[str] = []
    merged = concat_musicxml([a, bad, c], warnings=warnings)
    nums = _measure_numbers(merged)
    # The bad chunk lacks <part>, so it contributes nothing — only a + c are merged.
    assert nums["P1"] == [1, 2, 3, 4]


def test_part_count_mismatch_records_warning_but_appends() -> None:
    a = _score([[1, 2], [1, 2]])
    b = _score([[1]])  # only one part
    warnings: list[str] = []
    merged = concat_musicxml([a, b], warnings=warnings)
    nums = _measure_numbers(merged)
    assert nums["P1"] == [1, 2, 3]
    assert any("パート数" in w for w in warnings)


def test_empty_chunk_list_returns_empty_string() -> None:
    assert concat_musicxml([]) == ""
    assert concat_musicxml(["", ""]) == ""
