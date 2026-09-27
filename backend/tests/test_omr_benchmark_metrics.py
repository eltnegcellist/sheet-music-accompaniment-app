from app.benchmark.metrics import compare_musicxml


def _score(second_pitch: str = "D", second_duration: int = 1) -> str:
    return f"""
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>1</duration><type>quarter</type>
      </note>
      <note>
        <pitch><step>{second_pitch}</step><octave>4</octave></pitch>
        <duration>{second_duration}</duration>
        <type>{"quarter" if second_duration == 1 else "half"}</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""


def test_identical_score_is_perfect():
    metrics = compare_musicxml(_score(), _score())
    assert metrics["note_exact_f1"] == 1.0
    assert metrics["onset_pitch_f1"] == 1.0
    assert metrics["rhythm_f1"] == 1.0
    assert metrics["playback_score"] == 1.0
    assert metrics["gross_failure"] is False


def test_pitch_error_lowers_note_accuracy_but_not_rhythm():
    metrics = compare_musicxml(_score(second_pitch="E"), _score())
    assert metrics["note_exact_f1"] == 0.5
    assert metrics["onset_pitch_f1"] == 0.5
    assert metrics["rhythm_f1"] == 1.0


def test_duration_error_is_visible_in_exact_and_rhythm_metrics():
    metrics = compare_musicxml(_score(second_duration=2), _score())
    assert metrics["note_exact_f1"] < 1.0
    assert metrics["rhythm_f1"] < 1.0
