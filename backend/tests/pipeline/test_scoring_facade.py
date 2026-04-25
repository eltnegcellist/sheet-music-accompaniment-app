"""Tests for evaluate_musicxml_metrics — the /analyze surface helper."""

from app.pipeline.scoring_facade import evaluate_musicxml_metrics


_GOOD = """<score-partwise><part-list><score-part id="P1"/></part-list>
<part id="P1">
<measure number="1">
<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration><type>quarter</type></note>
</measure>
</part></score-partwise>"""


_REQUIRED_KEYS = {
    "final_score",
    "measure_duration_match",
    "in_range",
    "density",
    "key_consistency",
    "structure_consistency",
    "edits_penalty",
}


def test_returns_dict_with_all_phase4_keys():
    metrics = evaluate_musicxml_metrics(_GOOD)
    assert metrics is not None
    assert set(metrics) == _REQUIRED_KEYS


def test_returns_none_for_empty_input():
    assert evaluate_musicxml_metrics("") is None
    assert evaluate_musicxml_metrics("   ") is None


def test_returns_none_for_unparseable_xml():
    # Best-effort: bad XML must not raise — we just degrade to None so
    # /analyze can still respond with the OMR portion.
    assert evaluate_musicxml_metrics("<not closed") is None


def test_returns_none_for_invalid_weights():
    bad_weights = {
        "measure_duration_match": 0.5, "in_range": 0.5,
        "density": 0.5, "key_consistency": 0.5, "structure_consistency": 0.5,
    }  # sum == 2.5
    assert evaluate_musicxml_metrics(_GOOD, weights=bad_weights) is None


def test_final_score_is_within_unit_range():
    metrics = evaluate_musicxml_metrics(_GOOD)
    assert metrics is not None
    assert 0.0 <= metrics["final_score"] <= 1.0
