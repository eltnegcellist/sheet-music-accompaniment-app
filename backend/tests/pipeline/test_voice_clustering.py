"""Tests for onset clustering + voice assignment helpers (Phase 3-5)."""

import pytest

from app.pipeline.postprocess.voice import (
    OnsetCluster,
    OnsetEvent,
    VoiceAssignment,
    assign_voices_piano,
    chord_groups,
    cluster_onsets,
    reassignment_rate,
)


def _ev(idx, on, dur=1.0, pitch=60, staff=1, rest=False):
    return OnsetEvent(
        index=idx,
        onset_ql=on,
        duration_ql=dur,
        pitch_midi=None if rest else pitch,
        staff=staff,
        is_rest=rest,
    )


# --- cluster_onsets ------------------------------------------------------


def test_cluster_groups_close_onsets_within_tolerance():
    events = [_ev(0, 0.0), _ev(1, 0.05), _ev(2, 1.0)]
    clusters = cluster_onsets(events, tolerance_ql=0.1)
    assert len(clusters) == 2
    assert clusters[0].member_indices == [0, 1]
    assert clusters[1].member_indices == [2]


def test_cluster_uses_earliest_as_anchor():
    events = [_ev(0, 0.05), _ev(1, 0.0)]
    clusters = cluster_onsets(events, tolerance_ql=0.1)
    assert clusters[0].onset_ql == 0.0


def test_cluster_with_zero_tolerance_only_groups_exact_matches():
    events = [_ev(0, 0.0), _ev(1, 0.0001), _ev(2, 0.0)]
    clusters = cluster_onsets(events, tolerance_ql=0.0)
    # 0.0001 is within 1e-9 epsilon — but two strict 0.0 entries cluster.
    assert any(len(c.member_indices) == 2 for c in clusters)


def test_cluster_empty_input_returns_empty_list():
    assert cluster_onsets([], tolerance_ql=0.05) == []


def test_cluster_negative_tolerance_rejected():
    with pytest.raises(ValueError):
        cluster_onsets([_ev(0, 0.0)], tolerance_ql=-0.1)


# --- chord_groups -------------------------------------------------------


def test_chord_only_when_duration_and_staff_match():
    events = [
        _ev(0, 0.0, dur=1.0, pitch=60, staff=1),
        _ev(1, 0.0, dur=1.0, pitch=64, staff=1),  # chordable with 0
        _ev(2, 0.0, dur=0.5, pitch=67, staff=1),  # different duration
        _ev(3, 0.0, dur=1.0, pitch=72, staff=2),  # different staff
    ]
    clusters = cluster_onsets(events, tolerance_ql=0.05)
    chords = chord_groups(events, clusters)
    # The (dur=1.0, staff=1) bucket has indices 0 and 1.
    assert any(set(g) == {0, 1} for g in chords)
    # No bucket of size 1 leaks into the result.
    assert all(len(g) >= 2 for g in chords)


def test_chord_groups_rejects_rests():
    events = [
        _ev(0, 0.0, rest=True),
        _ev(1, 0.0, dur=1.0, pitch=60),
        _ev(2, 0.0, dur=1.0, pitch=64),
    ]
    chords = chord_groups(events, cluster_onsets(events, tolerance_ql=0.05))
    assert chords == [[1, 2]]


def test_singleton_clusters_produce_no_chords():
    events = [_ev(0, 0.0), _ev(1, 1.0)]
    chords = chord_groups(events, cluster_onsets(events, tolerance_ql=0.05))
    assert chords == []


# --- assign_voices_piano ------------------------------------------------


def test_staff_hint_wins_over_pitch_threshold():
    events = [_ev(0, 0.0, pitch=72, staff=2)]  # high pitch but staff=2 (LH)
    out = assign_voices_piano(events)
    assert out[0].voice == 2


def test_pitch_threshold_used_when_staff_unknown():
    events = [
        _ev(0, 0.0, pitch=72, staff=0),  # high
        _ev(1, 0.0, pitch=48, staff=0),  # low
    ]
    out = assign_voices_piano(events, split_pitch_midi=60)
    assert {va.note_index: va.voice for va in out} == {0: 1, 1: 2}


def test_assign_skips_rests():
    events = [_ev(0, 0.0, rest=True)]
    assert assign_voices_piano(events) == []


# --- reassignment_rate --------------------------------------------------


def test_reassignment_rate_zero_when_unchanged():
    before = {0: 1, 1: 2}
    after = [VoiceAssignment(0, 1), VoiceAssignment(1, 2)]
    assert reassignment_rate(before, after) == 0.0


def test_reassignment_rate_one_when_all_swapped():
    before = {0: 1, 1: 1}
    after = [VoiceAssignment(0, 2), VoiceAssignment(1, 2)]
    assert reassignment_rate(before, after) == 1.0


def test_reassignment_rate_ignores_unmatched_indices():
    before = {0: 1}
    after = [VoiceAssignment(0, 1), VoiceAssignment(99, 2)]  # 99 has no `before`
    assert reassignment_rate(before, after) == 0.0
