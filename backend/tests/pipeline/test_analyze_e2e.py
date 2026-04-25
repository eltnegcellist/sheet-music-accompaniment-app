"""E2E tests that hit /analyze through the FastAPI test client.

We don't have Audiveris in CI, so these tests use the user-MusicXML
branch (which skips Audiveris entirely). The point is to prove that
W-02's main.py changes haven't broken the pipeline_metrics surface or
the param_set_id field.
"""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


_VALID_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Solo</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>4</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
      <note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
      <note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>"""


def test_analyze_user_xml_returns_pipeline_metrics():
    """User-XML branch still gets scored — pipeline_metrics not None."""
    files = {
        "music_xml": (
            "test.musicxml",
            BytesIO(_VALID_MUSICXML.encode("utf-8")),
            "application/xml",
        ),
    }
    resp = client.post("/analyze", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pipeline_metrics"] is not None
    assert "final_score" in body["pipeline_metrics"]
    # All 6 sub-scores surface for the frontend.
    for k in (
        "measure_duration_match", "in_range", "density",
        "key_consistency", "structure_consistency", "edits_penalty",
    ):
        assert k in body["pipeline_metrics"], f"missing metric {k}"


def test_analyze_user_xml_records_active_param_set():
    files = {
        "music_xml": ("test.musicxml", BytesIO(_VALID_MUSICXML.encode("utf-8")), "application/xml"),
    }
    resp = client.post("/analyze", files=files)
    body = resp.json()
    # The default points at v3 (postprocess on); the env var or YAML
    # contents may decorate the id with a sha — check the prefix only.
    assert body["param_set_id"] is not None
    assert body["param_set_id"].startswith("v3")


def test_analyze_no_inputs_400s():
    """Sanity: omitting both pdf and music_xml is a 400, not a 500."""
    resp = client.post("/analyze")
    assert resp.status_code == 400


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
