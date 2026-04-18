from app.music.accompaniment import find_accompaniment_part


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
