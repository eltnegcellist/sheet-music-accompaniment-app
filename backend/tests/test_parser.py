from app.music.parser import extract_divisions_and_tempo


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


def test_sound_tempo_wins_over_words():
    xml = _score(
        """<measure number="1">
        <attributes><divisions>240</divisions></attributes>
        <direction><direction-type><words>Andantino</words></direction-type></direction>
        <sound tempo="88"/>
      </measure>"""
    )
    divisions, bpm = extract_divisions_and_tempo(xml)
    assert divisions == 240
    assert bpm == 88.0


def test_metronome_quarter_per_minute():
    xml = _score(
        """<measure number="1">
        <attributes><divisions>480</divisions></attributes>
        <direction><direction-type><metronome>
          <beat-unit>quarter</beat-unit><per-minute>72</per-minute>
        </metronome></direction-type></direction>
      </measure>"""
    )
    _, bpm = extract_divisions_and_tempo(xml)
    assert bpm == 72.0


def test_metronome_half_note_normalized_to_quarter():
    xml = _score(
        """<measure number="1">
        <attributes><divisions>480</divisions></attributes>
        <direction><direction-type><metronome>
          <beat-unit>half</beat-unit><per-minute>60</per-minute>
        </metronome></direction-type></direction>
      </measure>"""
    )
    _, bpm = extract_divisions_and_tempo(xml)
    assert bpm == 120.0


def test_metronome_dotted_quarter():
    xml = _score(
        """<measure number="1">
        <attributes><divisions>480</divisions></attributes>
        <direction><direction-type><metronome>
          <beat-unit>quarter</beat-unit><beat-unit-dot/><per-minute>80</per-minute>
        </metronome></direction-type></direction>
      </measure>"""
    )
    _, bpm = extract_divisions_and_tempo(xml)
    assert bpm == 120.0


def test_word_andantino_maps_to_bpm():
    xml = _score(
        """<measure number="1">
        <attributes><divisions>480</divisions></attributes>
        <direction><direction-type><words>Andantino</words></direction-type></direction>
      </measure>"""
    )
    _, bpm = extract_divisions_and_tempo(xml)
    assert bpm == 90.0


def test_word_allegro_moderato_beats_allegro():
    xml = _score(
        """<measure number="1">
        <attributes><divisions>480</divisions></attributes>
        <direction><direction-type><words>Allegro moderato</words></direction-type></direction>
      </measure>"""
    )
    _, bpm = extract_divisions_and_tempo(xml)
    assert bpm == 118.0


def test_credit_words_tempo():
    # Audiveris often emits top-of-page tempo markings as <credit-words>
    # rather than <direction><words>.
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <credit page="1">
    <credit-type>other</credit-type>
    <credit-words default-x="600" default-y="1700">Andantino</credit-words>
  </credit>
  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>480</divisions></attributes>
    </measure>
  </part>
</score-partwise>
"""
    _, bpm = extract_divisions_and_tempo(xml)
    assert bpm == 90.0


def test_uppercase_tempo_word():
    xml = _score(
        """<measure number="1">
        <attributes><divisions>480</divisions></attributes>
        <direction><direction-type><words>ANDANTINO</words></direction-type></direction>
      </measure>"""
    )
    _, bpm = extract_divisions_and_tempo(xml)
    assert bpm == 90.0


def test_tempo_word_with_punctuation():
    # "Andantino." or "Andantino (q = 90)" should still match.
    xml = _score(
        """<measure number="1">
        <attributes><divisions>480</divisions></attributes>
        <direction><direction-type><words>Andantino.</words></direction-type></direction>
      </measure>"""
    )
    _, bpm = extract_divisions_and_tempo(xml)
    assert bpm == 90.0


def test_defaults_when_no_tempo_information():
    xml = _score(
        """<measure number="1">
        <attributes><divisions>480</divisions></attributes>
      </measure>"""
    )
    _, bpm = extract_divisions_and_tempo(xml)
    assert bpm == 120.0
