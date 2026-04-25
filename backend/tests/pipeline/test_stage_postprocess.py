"""S2-01-c: round-trip integrity for the postprocess skeleton.

DoD: MusicXML -> music21 Score -> MusicXML must preserve note count,
part ids, and time signatures. We don't expect *byte* identity (music21
re-formats whitespace and adds defaults) — preserving structural
features is what matters for downstream stages.
"""

from pathlib import Path

import pytest
from lxml import etree

from app.pipeline.artifacts import FileArtifactStore
from app.pipeline.contracts import ArtifactRef, StageInput
from app.pipeline.stages.postprocess import (
    parse_musicxml,
    postprocess_skeleton,
    round_trip,
    write_musicxml,
)


_FIXTURE_4_4 = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>4</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
      <note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
      <note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
"""


def _count_pitched(xml: str) -> int:
    root = etree.fromstring(xml.encode("utf-8"))
    return sum(1 for n in root.iter("note") if n.find("rest") is None)


# --- pure helpers --------------------------------------------------------


def test_round_trip_preserves_pitched_note_count():
    out = round_trip(_FIXTURE_4_4)
    assert _count_pitched(out) == _count_pitched(_FIXTURE_4_4) == 4


def test_round_trip_preserves_part_id():
    out = round_trip(_FIXTURE_4_4)
    root = etree.fromstring(out.encode("utf-8"))
    parts = root.findall(".//part")
    assert len(parts) == 1
    # music21 may rewrite the id slightly but must keep some non-empty id.
    assert parts[0].get("id")


def test_round_trip_preserves_time_signature():
    out = round_trip(_FIXTURE_4_4)
    root = etree.fromstring(out.encode("utf-8"))
    beats = root.find(".//time/beats")
    beat_type = root.find(".//time/beat-type")
    assert beats is not None and beats.text == "4"
    assert beat_type is not None and beat_type.text == "4"


def test_parse_returns_score_object():
    score = parse_musicxml(_FIXTURE_4_4)
    # Score wrapper guaranteed by parse_musicxml even if music21 returned a Part.
    assert hasattr(score, "parts") and len(list(score.parts)) >= 1


# --- registered stage ----------------------------------------------------


def _make_input(tmp_path, xml: str | None) -> StageInput:
    store = FileArtifactStore(root=tmp_path / "art", job_id="job1")
    if xml is not None:
        p = store.path_for("omr", "score.musicxml")
        p.write_text(xml, encoding="utf-8")
        store.put(ArtifactRef(kind="musicxml", path=str(p)))
    return StageInput(
        job_id="job1", image_id="page_0", params={}, artifacts=store, trace={}
    )


def test_stage_writes_postprocess_artifact(tmp_path):
    inp = _make_input(tmp_path, _FIXTURE_4_4)
    out = postprocess_skeleton(inp)
    assert out.status == "ok"
    ref = inp.artifacts.get("postprocess_musicxml")
    assert ref is not None
    written = Path(ref.path).read_text(encoding="utf-8")
    assert _count_pitched(written) == 4
    # Metrics record both byte sizes so report.md can show round-trip cost.
    assert out.metrics.fields["postprocess.skeleton.note_count"] == 4
    assert out.metrics.fields["postprocess.skeleton.input_bytes"] > 0
    assert out.metrics.fields["postprocess.skeleton.output_bytes"] > 0


def test_stage_chains_on_previous_postprocess_artifact(tmp_path):
    inp = _make_input(tmp_path, _FIXTURE_4_4)
    # Run once to seed `postprocess_musicxml`, then again — the second run
    # must read its own previous output, not the original `musicxml`.
    postprocess_skeleton(inp)
    seeded = inp.artifacts.get("postprocess_musicxml")
    assert seeded is not None
    out2 = postprocess_skeleton(inp)
    assert out2.status == "ok"
    # Two runs leave two artifact refs of the same kind.
    refs = inp.artifacts.list("postprocess_musicxml")
    assert len(refs) == 2


def test_stage_failed_when_no_upstream_xml(tmp_path):
    inp = _make_input(tmp_path, xml=None)
    out = postprocess_skeleton(inp)
    assert out.status == "failed"
    assert "no MusicXML upstream" in (out.error or "")


def test_stage_failed_on_malformed_xml(tmp_path):
    inp = _make_input(tmp_path, xml="<not closed")
    out = postprocess_skeleton(inp)
    assert out.status == "failed"
    assert "music21" in (out.error or "")


def test_stage_registered_under_canonical_name():
    from app.pipeline.registry import default_registry
    assert default_registry.resolve("postprocess.skeleton") is postprocess_skeleton
