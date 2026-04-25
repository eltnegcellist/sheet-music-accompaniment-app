"""Postprocess stage — Phase 3 entry point.

This first cut wires music21 into the pipeline as a no-op pass:
  MusicXML (artifact: musicxml) -> music21 Score -> MusicXML (artifact: postprocess_musicxml)

The Score is the canonical in-memory representation that downstream
sub-stages (rhythm_fix, voice_rebuild, …) operate on. Putting that
round-trip behind a registered stage means later sub-stages can be
inserted without re-plumbing main.py.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Callable

from music21 import converter, stream

from ..contracts import (
    ArtifactRef,
    StageInput,
    StageMetrics,
    StageOutput,
)
from ..postprocess.edits import EditLog
from ..postprocess.rhythm import analyse_measures, measure_duration_match_rate
from ..postprocess.rhythm_fix import fix_rhythm
from ..postprocess.voice_rebuild import rebuild_voices
from ..registry import register


def parse_musicxml(xml: str) -> stream.Score:
    """Parse a MusicXML string into a music21 Score.

    music21 sometimes returns a `Part` for single-part docs; we always
    wrap into a Score so callers can rely on the same shape.
    """
    parsed = converter.parseData(xml, format="musicxml")
    if isinstance(parsed, stream.Score):
        return parsed
    score = stream.Score()
    score.append(parsed)
    return score


def write_musicxml(score: stream.Score) -> str:
    """Serialise a music21 Score back to a MusicXML string.

    `write()` returns a Path; we read it back and clean it up so callers
    work with bytes-in/bytes-out semantics. The temp file is best-effort —
    music21 manages its own temp dir.
    """
    target = score.write("musicxml")
    target_path = Path(target)
    try:
        return target_path.read_text(encoding="utf-8")
    finally:
        try:
            target_path.unlink(missing_ok=True)
        except OSError:
            # music21 sometimes shares the file across worker threads; not
            # cleaning up is preferable to swallowing real errors elsewhere.
            pass


def round_trip(xml: str) -> str:
    """Convenience: parse + write (used by tests and stages)."""
    return write_musicxml(parse_musicxml(xml))


def _resolve_input_xml(inp: StageInput) -> str | None:
    """Pick up MusicXML from the most recently produced artifact.

    Postprocess sub-stages chain in order so the *latest* postprocess
    artifact wins; fall back to the OMR stage's `musicxml` artifact for
    the first sub-stage in the chain.
    """
    for kind in ("postprocess_musicxml", "musicxml"):
        ref = inp.artifacts.get(kind)
        if ref is not None:
            return Path(ref.path).read_text(encoding="utf-8")
    return None


@register("postprocess.skeleton")
def postprocess_skeleton(inp: StageInput) -> StageOutput:
    """Phase 3 round-trip stub — proves the music21 plumbing works.

    Later sub-stages replace the body with real edits; the artifact
    contract (`postprocess_musicxml`) stays the same.
    """
    xml = _resolve_input_xml(inp)
    if xml is None:
        return StageOutput(
            status="failed",
            error="postprocess.skeleton: no MusicXML upstream",
        )

    try:
        score = parse_musicxml(xml)
        out_xml = write_musicxml(score)
    except Exception as exc:  # noqa: BLE001 — music21 raises a wide variety
        return StageOutput(
            status="failed",
            error=f"music21 round-trip failed: {type(exc).__name__}: {exc}",
        )

    out_path = inp.artifacts.path_for("postprocess", "round_trip.musicxml")
    out_path.write_text(out_xml, encoding="utf-8")
    ref = inp.artifacts.put(
        ArtifactRef(kind="postprocess_musicxml", path=str(out_path))
    )

    return StageOutput(
        status="ok",
        artifact_refs=[ref],
        metrics=StageMetrics(
            fields={
                "postprocess.skeleton.input_bytes": len(xml),
                "postprocess.skeleton.output_bytes": len(out_xml),
                "postprocess.skeleton.note_count": _count_pitched_notes(score),
            }
        ),
    )


def _count_pitched_notes(score: stream.Score) -> int:
    return sum(1 for n in score.flatten().notes if not n.isRest)


@register("postprocess.rhythm_fix")
def postprocess_rhythm_fix(inp: StageInput) -> StageOutput:
    """Phase 3-1 rhythm fix.

    Reads MusicXML upstream, applies the minimum-edit DP per measure,
    writes the corrected MusicXML + the edit log to the artifact store.
    Disabled by default (`params.postprocess.rhythm_fix.enabled: false`)
    so the v1_baseline params keep current behaviour.
    """
    cfg = inp.params.get("postprocess", {}).get("rhythm_fix", {}) or {}
    if not cfg.get("enabled", False):
        return StageOutput(
            status="skipped",
            metrics=StageMetrics(
                fields={"postprocess.rhythm_fix.enabled": False}
            ),
        )

    xml = _resolve_input_xml(inp)
    if xml is None:
        return StageOutput(
            status="failed",
            error="postprocess.rhythm_fix: no MusicXML upstream",
        )

    try:
        score = parse_musicxml(xml)
    except Exception as exc:  # noqa: BLE001
        return StageOutput(
            status="failed",
            error=f"music21 parse failed: {type(exc).__name__}: {exc}",
        )

    pre_records = analyse_measures(score)
    pre_match = measure_duration_match_rate(pre_records)

    log_path = inp.artifacts.path_for("postprocess", "edits.jsonl")
    log = EditLog(path=log_path)

    report = fix_rhythm(
        score,
        snap_durations=cfg.get("snap_durations", [1, 2, 4, 8, 16]),
        max_edits_per_measure=int(cfg.get("max_edits_per_measure", 4)),
        log=log,
    )
    log.flush()

    post_records = analyse_measures(score)
    post_match = measure_duration_match_rate(post_records)

    try:
        out_xml = write_musicxml(score)
    except Exception as exc:  # noqa: BLE001
        return StageOutput(
            status="failed",
            error=f"music21 write failed after fix: {type(exc).__name__}: {exc}",
        )

    out_path = inp.artifacts.path_for("postprocess", "rhythm_fix.musicxml")
    out_path.write_text(out_xml, encoding="utf-8")
    refs = [
        inp.artifacts.put(
            ArtifactRef(kind="postprocess_musicxml", path=str(out_path))
        ),
        inp.artifacts.put(
            ArtifactRef(kind="postprocess_edits", path=str(log_path))
        ),
    ]

    metrics = StageMetrics(
        fields={
            "postprocess.rhythm_fix.enabled": True,
            "postprocess.rhythm_fix.measures_total": report.measures_total,
            "postprocess.rhythm_fix.measures_fixed": report.measures_fixed,
            "postprocess.rhythm_fix.measures_unfixable": report.measures_unfixable,
            "postprocess.rhythm_fix.edits_total": sum(report.actions_by_kind.values()),
            "postprocess.rhythm_fix.match_rate_before": round(pre_match, 4),
            "postprocess.rhythm_fix.match_rate_after": round(post_match, 4),
        }
    )
    for kind, count in report.actions_by_kind.items():
        metrics.fields[f"postprocess.rhythm_fix.op.{kind}"] = count

    return StageOutput(status="ok", artifact_refs=refs, metrics=metrics)


@register("postprocess.voice_rebuild")
def postprocess_voice_rebuild(inp: StageInput) -> StageOutput:
    """Phase 3-5 RH/LH voice rebuild with rollback guard.

    Disabled by default. Reads the upstream MusicXML, proposes voice
    assignments, and either applies them or records a rollback edit.
    The on-disk MusicXML is rewritten either way so downstream stages
    (evaluator, merger) consume a consistent artifact.
    """
    cfg = inp.params.get("postprocess", {}).get("voice_rebuild", {}) or {}
    if not cfg.get("enabled", False):
        return StageOutput(
            status="skipped",
            metrics=StageMetrics(
                fields={"postprocess.voice_rebuild.enabled": False}
            ),
        )

    xml = _resolve_input_xml(inp)
    if xml is None:
        return StageOutput(
            status="failed",
            error="postprocess.voice_rebuild: no MusicXML upstream",
        )

    try:
        score = parse_musicxml(xml)
    except Exception as exc:  # noqa: BLE001
        return StageOutput(
            status="failed",
            error=f"music21 parse failed: {type(exc).__name__}: {exc}",
        )

    log_path = inp.artifacts.path_for("postprocess", "voice_edits.jsonl")
    log = EditLog(path=log_path)
    report = rebuild_voices(
        score,
        log=log,
        rollback_rate_threshold=float(cfg.get("rollback_rate_threshold", 0.30)),
        split_pitch_midi=int(cfg.get("split_pitch_midi", 60)),
    )
    log.flush()

    try:
        out_xml = write_musicxml(score)
    except Exception as exc:  # noqa: BLE001
        return StageOutput(
            status="failed",
            error=f"music21 write failed after voice rebuild: {type(exc).__name__}: {exc}",
        )

    out_path = inp.artifacts.path_for("postprocess", "voice_rebuild.musicxml")
    out_path.write_text(out_xml, encoding="utf-8")
    refs = [
        inp.artifacts.put(
            ArtifactRef(kind="postprocess_musicxml", path=str(out_path))
        ),
        inp.artifacts.put(
            ArtifactRef(kind="postprocess_voice_edits", path=str(log_path))
        ),
    ]
    metrics = StageMetrics(
        fields={
            "postprocess.voice_rebuild.enabled": True,
            "postprocess.voice_rebuild.notes_total": report.notes_total,
            "postprocess.voice_rebuild.notes_reassigned": report.notes_reassigned,
            "postprocess.voice_rebuild.reassignment_rate": round(
                report.reassignment_rate, 4
            ),
            "postprocess.voice_rebuild.rollback": report.rollback,
            "postprocess.voice_rebuild.parts_processed": len(report.parts_processed),
        }
    )
    return StageOutput(status="ok", artifact_refs=refs, metrics=metrics)
