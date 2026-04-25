"""Onset clustering + chord aggregation primitives (Phase 3-5-a/b).

We don't touch music21 directly here — these helpers operate on simple
DTOs so the unit tests stay fast and exercise the policy independently
of music21's mutation API. The voice-rebuild stage maps the policy
output back onto the score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class OnsetEvent:
    """A single note's onset within a measure-voice.

    `index` is the position within the source list so the applier can
    map clusters back to the actual notes; `pitch_midi` lets the chord
    aggregator deduplicate unisons.
    """

    index: int
    onset_ql: float
    duration_ql: float
    pitch_midi: int | None  # None for rests
    staff: int = 1
    is_rest: bool = False


@dataclass
class OnsetCluster:
    """A group of `OnsetEvent`s that should be considered simultaneous."""

    onset_ql: float
    member_indices: list[int]


def cluster_onsets(
    events: list[OnsetEvent],
    *,
    tolerance_ql: float,
) -> list[OnsetCluster]:
    """Greedy 1D clustering by onset proximity.

    `tolerance_ql` is the maximum gap between consecutive events to
    keep them in the same cluster. Phase 3-5-b uses staff_space-derived
    pixel ranges; we work in qL because the score is already parsed.

    Events are processed in onset order. Within each cluster we use the
    earliest onset as the canonical onset_ql so the applier knows where
    to anchor the chord — the plan's "minimum onset" rule.
    """
    if not events:
        return []
    if tolerance_ql < 0:
        raise ValueError("tolerance_ql must be >= 0")

    sorted_events = sorted(events, key=lambda e: e.onset_ql)
    clusters: list[OnsetCluster] = []
    current_anchor = sorted_events[0].onset_ql
    current: list[int] = []

    for ev in sorted_events:
        if ev.onset_ql - current_anchor <= tolerance_ql + 1e-9:
            current.append(ev.index)
        else:
            clusters.append(
                OnsetCluster(onset_ql=current_anchor, member_indices=current)
            )
            current_anchor = ev.onset_ql
            current = [ev.index]
    if current:
        clusters.append(
            OnsetCluster(onset_ql=current_anchor, member_indices=current)
        )
    return clusters


def chord_groups(
    events: list[OnsetEvent],
    clusters: list[OnsetCluster],
    *,
    require_same_duration: bool = True,
    require_same_staff: bool = True,
) -> list[list[int]]:
    """Within each cluster, decide which notes form a real chord.

    The plan's 3-5-a rule: members must share both `duration_ql` and
    `staff` to chord-merge. Mismatched members stay independent — they
    become separate notes that share the cluster onset.
    """
    by_index = {ev.index: ev for ev in events}
    out: list[list[int]] = []
    for c in clusters:
        # Skip rests entirely — they never become chord members.
        members = [i for i in c.member_indices if not by_index[i].is_rest]
        if len(members) <= 1:
            continue
        # Group by (duration_ql, staff) so each compatible subset is its own chord.
        buckets: dict[tuple[float, int], list[int]] = {}
        for i in members:
            ev = by_index[i]
            key = (
                ev.duration_ql if require_same_duration else 0.0,
                ev.staff if require_same_staff else 1,
            )
            buckets.setdefault(key, []).append(i)
        for grp in buckets.values():
            if len(grp) > 1:
                out.append(grp)
    return out


@dataclass(frozen=True)
class VoiceAssignment:
    """Output of the RH/LH classifier: which voice each note belongs to."""

    note_index: int
    voice: int  # 1 = right hand, 2 = left hand


def assign_voices_piano(
    events: list[OnsetEvent],
    *,
    split_pitch_midi: int = 60,  # middle C
    pitch_override_band_semitones: int = 18,
) -> list[VoiceAssignment]:
    """Classify each (non-rest) event into RH (1) or LH (2).

    Policy (Phase 3-5-c lite):
      * Trust the staff hint by default — Audiveris labelling is usually
        right. This also matches the plan's "y 座標優先" rule.
      * Override the staff hint with the pitch threshold only when the
        disagreement is large (≥ `pitch_override_band_semitones` from the
        split). E.g. a C2 mis-tagged as staff=1 (RH) gets caught here.
      * When no staff hint exists (staff not in {1,2}), the pitch
        threshold decides directly.

    The rollback guard above this function catches degenerate proposals
    (huge swathes of notes flipping voices) and reverts them.
    """
    out: list[VoiceAssignment] = []
    for ev in events:
        if ev.is_rest or ev.pitch_midi is None:
            continue
        pitch_says = 1 if ev.pitch_midi >= split_pitch_midi else 2
        if ev.staff in (1, 2):
            far = abs(ev.pitch_midi - split_pitch_midi) >= pitch_override_band_semitones
            if far and ev.staff != pitch_says:
                voice = pitch_says
            else:
                voice = ev.staff
        else:
            voice = pitch_says
        out.append(VoiceAssignment(note_index=ev.index, voice=voice))
    return out


def reassignment_rate(
    before: dict[int, int], after: list[VoiceAssignment]
) -> float:
    """Fraction of indices whose voice assignment changed.

    `before` is `{note_index: voice}` from the source score; `after` is
    the proposed reassignment. Indices missing from either side count
    as unchanged so adding/removing notes doesn't blow up the metric.
    """
    if not after:
        return 0.0
    changed = 0
    counted = 0
    for va in after:
        if va.note_index in before:
            counted += 1
            if before[va.note_index] != va.voice:
                changed += 1
    if counted == 0:
        return 0.0
    return changed / counted
