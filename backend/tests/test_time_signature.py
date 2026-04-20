from app.music.parser import extract_time_signature


def _score(body: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1">
    {body}
  </part>
</score-partwise>
"""


def test_reads_two_four():
    xml = _score(
        """<measure number="1">
        <attributes>
          <divisions>1</divisions>
          <time><beats>2</beats><beat-type>4</beat-type></time>
        </attributes>
      </measure>"""
    )
    ts = extract_time_signature(xml)
    assert ts is not None
    assert ts.beats == 2
    assert ts.beat_type == 4


def test_reads_compound_six_eight():
    xml = _score(
        """<measure number="1">
        <attributes>
          <divisions>1</divisions>
          <time><beats>6</beats><beat-type>8</beat-type></time>
        </attributes>
      </measure>"""
    )
    ts = extract_time_signature(xml)
    assert ts is not None
    assert ts.beats == 6
    assert ts.beat_type == 8


def test_returns_none_when_time_missing():
    xml = _score(
        """<measure number="1">
        <attributes><divisions>1</divisions></attributes>
      </measure>"""
    )
    assert extract_time_signature(xml) is None


def test_takes_first_time_signature_only():
    # Meter changes mid-score are rare in solo+piano rep; we only report
    # the first signature (what the UI meter display can render anyway).
    xml = _score(
        """<measure number="1">
        <attributes>
          <divisions>1</divisions>
          <time><beats>3</beats><beat-type>4</beat-type></time>
        </attributes>
      </measure>
      <measure number="2">
        <attributes>
          <time><beats>4</beats><beat-type>4</beat-type></time>
        </attributes>
      </measure>"""
    )
    ts = extract_time_signature(xml)
    assert ts is not None
    assert ts.beats == 3
    assert ts.beat_type == 4
