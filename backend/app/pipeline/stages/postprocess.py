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
