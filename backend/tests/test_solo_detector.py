"""Tests for the solo-section detector.

We exercise the staff-line counter against synthetic PIL images and the
split-point selector against precomputed staff-count vectors. End-to-end
PDF rendering still requires poppler; that path is exercised by the
integration tests.
"""

from __future__ import annotations

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402

from app.pdf.solo_detector import (  # noqa: E402
    SoloSplitResult,
    count_staff_lines,
    pick_split_point,
)


def _make_page_with_staves(
    *, num_systems: int, staves_per_system: int, width: int = 600, height: int = 800
) -> Image.Image:
    """Render a synthetic page with `num_systems × staves_per_system` staves.

    Each staff is the standard 5 horizontal lines spaced 6px apart, with
    16px between staves of the same system and 60px between systems.
    """
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)
    line_spacing = 6
    intra_system_gap = 16
    inter_system_gap = 60
    margin_left = 40
    margin_right = width - 40
    y = 60
    for _system in range(num_systems):
        for _staff in range(staves_per_system):
            for line in range(5):
                draw.line(
                    [(margin_left, y + line * line_spacing), (margin_right, y + line * line_spacing)],
                    fill=0,
                    width=1,
                )
            y += line_spacing * 4 + intra_system_gap
        y += inter_system_gap - intra_system_gap
        if y > height - 40:
            break
    return img


def test_staff_line_count_solo_only_page() -> None:
    img = _make_page_with_staves(num_systems=6, staves_per_system=1)
    count = count_staff_lines(img)
    # 6 systems × 5 lines = 30 staff lines, give or take 1 for edge effects.
    assert 28 <= count <= 32


def test_staff_line_count_full_score_page() -> None:
    img = _make_page_with_staves(num_systems=4, staves_per_system=3)
    count = count_staff_lines(img)
    # 4 systems × 3 staves × 5 lines = 60 staff lines.
    assert 56 <= count <= 64


def test_staff_line_count_blank_page_is_zero() -> None:
    blank = Image.new("L", (400, 600), color=255)
    assert count_staff_lines(blank) == 0


def test_full_to_solo_transition_detected() -> None:
    # 3 full-score pages then 3 solo pages.
    counts = [60, 60, 55, 25, 30, 28]
    split = pick_split_point(counts)
    assert split == (3, False)


def test_solo_to_full_transition_detected() -> None:
    # 3 solo pages then 3 full-score pages — the previous heuristic missed
    # this entirely.
    counts = [25, 28, 30, 60, 55, 60]
    split = pick_split_point(counts)
    assert split == (3, True)


def test_uniform_document_returns_no_split() -> None:
    counts = [60, 58, 62, 59, 60, 61]
    assert pick_split_point(counts) is None


def test_marginal_difference_below_threshold_skipped() -> None:
    # Lighter on second half, but only by ~10% — not strong enough.
    counts = [50, 50, 50, 45, 44, 45]
    assert pick_split_point(counts) is None


def test_split_picks_strongest_contrast() -> None:
    # A small dip at index 2 plus a strong drop at index 4 — the strong drop
    # should win because it has the largest staff-count gap.
    counts = [60, 60, 50, 60, 25, 24, 26]
    split = pick_split_point(counts)
    assert split == (4, False)


def test_solo_split_result_geometry() -> None:
    res = SoloSplitResult(
        full_start_page=0,
        full_end_page=3,
        solo_start_page=3,
        solo_end_page=6,
    )
    assert res.full_end_page - res.full_start_page == 3
    assert res.solo_end_page - res.solo_start_page == 3
    assert res.solo_at_front is False
