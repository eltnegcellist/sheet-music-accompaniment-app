import { describe, expect, it } from "vitest";

import { parseMusicXml } from "../musicXmlParser";

const SCORE = `<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>2</divisions></attributes>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>2</duration>
      </note>
      <note>
        <pitch><step>E</step><octave>4</octave></pitch>
        <duration>2</duration>
      </note>
    </measure>
    <measure number="2">
      <note>
        <pitch><step>G</step><alter>1</alter><octave>4</octave></pitch>
        <duration>4</duration>
      </note>
    </measure>
  </part>
</score-partwise>`;

describe("parseMusicXml", () => {
  it("emits notes with correct pitches and beat positions", () => {
    const { notes, measures } = parseMusicXml(SCORE, "P1");

    expect(notes).toHaveLength(3);
    expect(notes[0]).toMatchObject({ pitch: "C4", beat: 0, durationBeats: 1 });
    expect(notes[1]).toMatchObject({ pitch: "E4", beat: 1, durationBeats: 1 });
    expect(notes[2]).toMatchObject({
      pitch: "G#4",
      beat: 2,
      durationBeats: 2,
    });

    expect(measures).toEqual([
      { index: 1, startBeat: 0, lengthBeats: 2 },
      { index: 2, startBeat: 2, lengthBeats: 2 },
    ]);
  });

  it("pads a short measure up to the canonical length so subsequent measures stay aligned", () => {
    // Measures 1 and 3 are full 4-beat bars; measure 2 is short because OMR
    // dropped a note. Canonical = 4 (mode), so measure 2 gets padded and
    // measure 3 still starts at beat 8.
    const shortMeasure = `<?xml version="1.0"?>
<score-partwise><part-list><score-part id="P1"/></part-list><part id="P1">
  <measure number="1">
    <attributes>
      <divisions>1</divisions>
      <time><beats>4</beats><beat-type>4</beat-type></time>
    </attributes>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration></note>
  </measure>
  <measure number="2">
    <note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration></note>
    <note><pitch><step>E</step><octave>4</octave></pitch><duration>1</duration></note>
  </measure>
  <measure number="3">
    <note><pitch><step>F</step><octave>4</octave></pitch><duration>4</duration></note>
  </measure>
</part></score-partwise>`;
    const { notes, measures } = parseMusicXml(shortMeasure, "P1");
    expect(measures[0]).toEqual({ index: 1, startBeat: 0, lengthBeats: 4 });
    expect(measures[1]).toEqual({ index: 2, startBeat: 4, lengthBeats: 4 });
    expect(measures[2]).toEqual({ index: 3, startBeat: 8, lengthBeats: 4 });
    expect(notes[notes.length - 1]).toMatchObject({ pitch: "F4", beat: 8 });
  });

  it("quantizes outlier over-length measures so downstream bars don't drift", () => {
    // Three 2-beat bars and one 2.5-beat outlier (Audiveris sometimes emits an
    // extra note). Canonical = 2 (mode). Measure 4 must still start at beat 6,
    // not 6.5 — otherwise every subsequent beat would be offset by half a beat.
    const outlier = `<?xml version="1.0"?>
<score-partwise><part-list><score-part id="P1"/></part-list><part id="P1">
  <measure number="1">
    <attributes>
      <divisions>2</divisions>
      <time><beats>2</beats><beat-type>4</beat-type></time>
    </attributes>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration></note>
  </measure>
  <measure number="2">
    <note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration></note>
  </measure>
  <measure number="3">
    <note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration></note>
    <note><pitch><step>F</step><octave>4</octave></pitch><duration>1</duration></note>
  </measure>
  <measure number="4">
    <note><pitch><step>G</step><octave>4</octave></pitch><duration>4</duration></note>
  </measure>
</part></score-partwise>`;
    const { notes, measures } = parseMusicXml(outlier, "P1");
    expect(measures).toEqual([
      { index: 1, startBeat: 0, lengthBeats: 2 },
      { index: 2, startBeat: 2, lengthBeats: 2 },
      { index: 3, startBeat: 4, lengthBeats: 2 },
      { index: 4, startBeat: 6, lengthBeats: 2 },
    ]);
    // The last note of the outlier measure is allowed past the canonical edge;
    // what matters is the following measure starts on the grid.
    const g4 = notes.find((n) => n.pitch === "G4");
    expect(g4?.beat).toBe(6);
  });

  it("leaves implicit (pickup) measures short", () => {
    const anacrusis = `<?xml version="1.0"?>
<score-partwise><part-list><score-part id="P1"/></part-list><part id="P1">
  <measure number="0" implicit="yes">
    <attributes>
      <divisions>1</divisions>
      <time><beats>4</beats><beat-type>4</beat-type></time>
    </attributes>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration></note>
  </measure>
  <measure number="1">
    <note><pitch><step>D</step><octave>4</octave></pitch><duration>4</duration></note>
  </measure>
</part></score-partwise>`;
    const { measures } = parseMusicXml(anacrusis, "P1");
    expect(measures[0]).toEqual({ index: 0, startBeat: 0, lengthBeats: 1 });
    expect(measures[1].startBeat).toBe(1);
  });

  it("collapses chord notes onto the same beat", () => {
    const chord = `<?xml version="1.0"?>
<score-partwise><part-list><score-part id="P1"/></part-list><part id="P1">
  <measure number="1">
    <attributes><divisions>1</divisions></attributes>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration></note>
    <note><chord/><pitch><step>E</step><octave>4</octave></pitch><duration>1</duration></note>
  </measure>
</part></score-partwise>`;
    const { notes } = parseMusicXml(chord, "P1");
    expect(notes).toHaveLength(2);
    expect(notes[0].beat).toBe(0);
    expect(notes[1].beat).toBe(0);
  });
});
