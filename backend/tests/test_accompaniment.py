from app.music.accompaniment import find_accompaniment_part, find_solo_part


SOLO_PIANO_DUET = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Violin</part-name></score-part>
    <score-part id="P2"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions></attributes>
      <note><rest/><duration>4</duration></note>
    </measure>
  </part>
  <part id="P2">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <staves>2</staves>
      </attributes>
      <note><rest/><duration>4</duration></note>
    </measure>
  </part>
</score-partwise>
"""


NAME_ONLY = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Flute</part-name></score-part>
    <score-part id="P2"><part-name>Klavier</part-name></score-part>
  </part-list>
  <part id="P1"><measure number="1"/></part>
  <part id="P2"><measure number="1"/></part>
</score-partwise>
"""


NO_HINT = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Voice</part-name></score-part>
    <score-part id="P2"><part-name>Strings</part-name></score-part>
  </part-list>
  <part id="P1"><measure number="1"/></part>
  <part id="P2"><measure number="1"/></part>
</score-partwise>
"""


def test_picks_two_staff_part():
    assert find_accompaniment_part(SOLO_PIANO_DUET) == "P2"


def test_falls_back_to_name_match():
    assert find_accompaniment_part(NAME_ONLY) == "P2"


def test_falls_back_to_last_part():
    assert find_accompaniment_part(NO_HINT) == "P2"


def test_find_solo_returns_other_part():
    # Accompaniment is P2 (piano); solo should be P1 (violin).
    assert find_solo_part(SOLO_PIANO_DUET, "P2") == "P1"


def test_find_solo_is_none_when_only_one_part():
    single = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1"><measure number="1"/></part>
</score-partwise>
"""
    assert find_solo_part(single, "P1") is None


def test_find_solo_is_none_when_accompaniment_unknown():
    assert find_solo_part(SOLO_PIANO_DUET, None) is None


def test_find_solo_prefers_note_dense_single_staff_part():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Noise</part-name></score-part>
    <score-part id="P2"><part-name>Piano</part-name></score-part>
    <score-part id="P3"><part-name>Viola</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration></note>
    </measure>
  </part>
  <part id="P2">
    <measure number="1">
      <attributes><staves>2</staves></attributes>
      <note><rest/><duration>4</duration></note>
    </measure>
  </part>
  <part id="P3">
    <measure number="1">
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration></note>
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>1</duration></note>
      <note><pitch><step>E</step><octave>5</octave></pitch><duration>1</duration></note>
    </measure>
  </part>
</score-partwise>
"""
    assert find_solo_part(xml, "P2") == "P3"
