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
from ..postprocess.key_estimation import estimate_key
from ..postprocess.key_signature import fix_dropped_key_accidentals
from ..postprocess.missing_measures import fill_missing_measures
from ..postprocess.pitch_fix import (
    fix_ngram_outliers,
    fix_octave_errors,
    fix_scale_outliers,
)
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


@register("postprocess.pitch_fix")
def postprocess_pitch_fix(inp: StageInput) -> StageOutput:
    """Phase 3-3 pitch correction: scale-outlier + n-gram + octave passes.

    Each sub-pass is independently togglable via params; all default to
    off so v1_baseline keeps shipping unchanged. The stage emits a
    single MusicXML artifact (`postprocess_musicxml`) plus its own
    edit log (`postprocess_pitch_edits`).
    """
    cfg = inp.params.get("postprocess", {}).get("pitch_fix", {}) or {}
    if not cfg.get("enabled", False):
        return StageOutput(
            status="skipped",
            metrics=StageMetrics(
                fields={"postprocess.pitch_fix.enabled": False}
            ),
        )

    xml = _resolve_input_xml(inp)
    if xml is None:
        return StageOutput(
            status="failed",
            error="postprocess.pitch_fix: no MusicXML upstream",
        )

    try:
        score = parse_musicxml(xml)
    except Exception as exc:  # noqa: BLE001
        return StageOutput(
            status="failed",
            error=f"music21 parse failed: {type(exc).__name__}: {exc}",
        )

    log_path = inp.artifacts.path_for("postprocess", "pitch_edits.jsonl")
    log = EditLog(path=log_path)

    # Phase 3-3-a: estimate key once. Sub-passes that need it gate on confidence.
    key = estimate_key(score)
    metrics_fields: dict[str, float | int | str | bool] = {
        "postprocess.pitch_fix.enabled": True,
        "postprocess.pitch_fix.key_tonic_pc": key.tonic_pc if key else -1,
        "postprocess.pitch_fix.key_mode": key.mode if key else "none",
        "postprocess.pitch_fix.key_confidence": (
            round(key.confidence, 4) if key else 0.0
        ),
    }

    if cfg.get("scale_outliers", {}).get("enabled", True) and key is not None:
        scale_cfg = cfg.get("scale_outliers", {}) or {}
        scale_report = fix_scale_outliers(
            score,
            key,
            log=log,
            confidence_floor=float(scale_cfg.get("confidence_floor", 0.6)),
            max_per_measure=int(scale_cfg.get("max_per_measure", 1)),
        )
        metrics_fields.update(
            {
                "postprocess.pitch_fix.scale.candidates": scale_report.candidates,
                "postprocess.pitch_fix.scale.corrected": scale_report.corrected,
                "postprocess.pitch_fix.scale.skipped_by_cap": (
                    scale_report.skipped_by_per_measure_cap
                ),
                "postprocess.pitch_fix.scale.skipped_explicit_accidental": (
                    scale_report.skipped_explicit_accidental
                ),
            }
        )

    if cfg.get("octave_errors", {}).get("enabled", True):
        oct_cfg = cfg.get("octave_errors", {}) or {}
        oct_report = fix_octave_errors(
            score,
            log=log,
            jump_threshold_semitones=int(oct_cfg.get("jump_threshold_semitones", 18)),
        )
        metrics_fields.update(
            {
                "postprocess.pitch_fix.octave.candidates": oct_report.candidates,
                "postprocess.pitch_fix.octave.corrected": oct_report.corrected,
            }
        )

    if cfg.get("ngram", {}).get("enabled", True):
        ng_cfg = cfg.get("ngram", {}) or {}
        ng_report = fix_ngram_outliers(
            score,
            log=log,
            max_ratio=float(ng_cfg.get("max_ratio", 0.02)),
            quantile=float(ng_cfg.get("quantile", 0.99)),
            correction_window_semitones=int(
                ng_cfg.get("correction_window_semitones", 1)
            ),
            min_cost_semitones=int(ng_cfg.get("min_cost_semitones", 6)),
        )
        metrics_fields.update(
            {
                "postprocess.pitch_fix.ngram.candidates": ng_report.candidates,
                "postprocess.pitch_fix.ngram.corrected": ng_report.corrected,
                "postprocess.pitch_fix.ngram.capped": ng_report.capped_by_max_ratio,
            }
        )

    log.flush()

    try:
        out_xml = write_musicxml(score)
    except Exception as exc:  # noqa: BLE001
        return StageOutput(
            status="failed",
            error=f"music21 write failed after pitch fix: {type(exc).__name__}: {exc}",
        )

    out_path = inp.artifacts.path_for("postprocess", "pitch_fix.musicxml")
    out_path.write_text(out_xml, encoding="utf-8")
    refs = [
        inp.artifacts.put(
            ArtifactRef(kind="postprocess_musicxml", path=str(out_path))
        ),
        inp.artifacts.put(
            ArtifactRef(kind="postprocess_pitch_edits", path=str(log_path))
        ),
    ]
    metrics_fields["postprocess.pitch_fix.edits_total"] = len(log)

    return StageOutput(
        status="ok",
        artifact_refs=refs,
        metrics=StageMetrics(fields=metrics_fields),
    )


@register("postprocess.fill_measures")
def postprocess_fill_measures(inp: StageInput) -> StageOutput:
    """Phase 3-8: insert empty placeholder measures for number-sequence gaps.

    Disabled by default. When enabled it should run BEFORE rhythm_fix so
    the inserted (full-bar rest) measures don't trip the duration-match
    metric on subsequent passes.
    """
    cfg = inp.params.get("postprocess", {}).get("fill_measures", {}) or {}
    if not cfg.get("enabled", False):
        return StageOutput(
            status="skipped",
            metrics=StageMetrics(
                fields={"postprocess.fill_measures.enabled": False}
            ),
        )

    xml = _resolve_input_xml(inp)
    if xml is None:
        return StageOutput(
            status="failed",
            error="postprocess.fill_measures: no MusicXML upstream",
        )

    try:
        score = parse_musicxml(xml)
    except Exception as exc:  # noqa: BLE001
        return StageOutput(
            status="failed",
            error=f"music21 parse failed: {type(exc).__name__}: {exc}",
        )

    log_path = inp.artifacts.path_for("postprocess", "missing_measure_edits.jsonl")
    log = EditLog(path=log_path)

    report = fill_missing_measures(
        score,
        log=log,
        max_gap_size=int(cfg.get("max_gap_size", 8)),
    )
    log.flush()

    try:
        out_xml = write_musicxml(score)
    except Exception as exc:  # noqa: BLE001
        return StageOutput(
            status="failed",
            error=f"music21 write failed after fill_measures: {type(exc).__name__}: {exc}",
        )

    out_path = inp.artifacts.path_for("postprocess", "fill_measures.musicxml")
    out_path.write_text(out_xml, encoding="utf-8")
    refs = [
        inp.artifacts.put(
            ArtifactRef(kind="postprocess_musicxml", path=str(out_path))
        ),
        inp.artifacts.put(
            ArtifactRef(kind="postprocess_missing_measure_edits", path=str(log_path))
        ),
    ]

    metrics = StageMetrics(
        fields={
            "postprocess.fill_measures.enabled": True,
            "postprocess.fill_measures.gaps_found": report.gaps_found,
            "postprocess.fill_measures.measures_inserted": report.measures_inserted,
            "postprocess.fill_measures.parts_processed": report.parts_processed,
        }
    )
    return StageOutput(status="ok", artifact_refs=refs, metrics=metrics)


@register("postprocess.fix_key_accidentals")
def postprocess_fix_key_accidentals(inp: StageInput) -> StageOutput:
    """Restore accidentals implied by the key signature but dropped by OMR.

    Targets the pattern Audiveris hits most often on real PDFs: a piece
    in G major where Audiveris emits `<step>F</step>` (no `<alter>`)
    despite the F being part of the key signature.

    Disabled by default. Should run AFTER fill_measures (so newly
    inserted measures inherit the right key context) but BEFORE rhythm_fix
    (so duration changes don't shift offsets while we re-walk).
    """
    cfg = inp.params.get("postprocess", {}).get("fix_key_accidentals", {}) or {}
    if not cfg.get("enabled", False):
        return StageOutput(
            status="skipped",
            metrics=StageMetrics(
                fields={"postprocess.fix_key_accidentals.enabled": False}
            ),
        )

    xml = _resolve_input_xml(inp)
    if xml is None:
        return StageOutput(
            status="failed",
            error="postprocess.fix_key_accidentals: no MusicXML upstream",
        )

    try:
        score = parse_musicxml(xml)
    except Exception as exc:  # noqa: BLE001
        return StageOutput(
            status="failed",
            error=f"music21 parse failed: {type(exc).__name__}: {exc}",
        )

    log_path = inp.artifacts.path_for("postprocess", "key_accidental_edits.jsonl")
    log = EditLog(path=log_path)
    report = fix_dropped_key_accidentals(score, log=log)
    log.flush()

    try:
        out_xml = write_musicxml(score)
    except Exception as exc:  # noqa: BLE001
        return StageOutput(
            status="failed",
            error=f"music21 write failed after fix_key_accidentals: {type(exc).__name__}: {exc}",
        )

    out_path = inp.artifacts.path_for("postprocess", "key_accidentals.musicxml")
    out_path.write_text(out_xml, encoding="utf-8")
    refs = [
        inp.artifacts.put(
            ArtifactRef(kind="postprocess_musicxml", path=str(out_path))
        ),
        inp.artifacts.put(
            ArtifactRef(kind="postprocess_key_accidental_edits", path=str(log_path))
        ),
    ]

    metrics = StageMetrics(
        fields={
            "postprocess.fix_key_accidentals.enabled": True,
            "postprocess.fix_key_accidentals.candidates_checked": report.candidates_checked,
            "postprocess.fix_key_accidentals.accidentals_restored": (
                report.accidentals_restored
            ),
            "postprocess.fix_key_accidentals.parts_processed": report.parts_processed,
        }
    )
    return StageOutput(status="ok", artifact_refs=refs, metrics=metrics)
