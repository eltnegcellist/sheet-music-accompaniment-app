import { describe, expect, it } from "vitest";

import { sanitizeForOsmd } from "../sanitize";

describe("sanitizeForOsmd", () => {
  it("removes <time> elements missing <beats> or <beat-type>", () => {
    const xml = `<?xml version="1.0"?>
<score-partwise><part-list><score-part id="P1"/></part-list><part id="P1">
  <measure number="1">
    <attributes>
      <divisions>1</divisions>
      <time/>
    </attributes>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration></note>
  </measure>
</part></score-partwise>`;
    const cleaned = sanitizeForOsmd(xml);
    expect(cleaned).not.toContain("<time/>");
    expect(cleaned).not.toContain("<time></time>");
  });

  it("removes <octave-shift> tags that crash OSMD", () => {
    const xml = `<?xml version="1.0"?>
<score-partwise><part-list><score-part id="P1"/></part-list><part id="P1">
  <measure number="1">
    <direction><direction-type><octave-shift type="up" size="8"/></direction-type></direction>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration></note>
  </measure>
</part></score-partwise>`;
    const cleaned = sanitizeForOsmd(xml);
    expect(cleaned).not.toContain("octave-shift");
  });

  it("repairs zero <divisions> to 1 rather than dropping the element", () => {
    const xml = `<?xml version="1.0"?>
<score-partwise><part-list><score-part id="P1"/></part-list><part id="P1">
  <measure number="1">
    <attributes><divisions>0</divisions></attributes>
  </measure>
</part></score-partwise>`;
    const cleaned = sanitizeForOsmd(xml);
    expect(cleaned).toMatch(/<divisions>1<\/divisions>/);
  });

  it("drops non-grace notes with no duration", () => {
    const xml = `<?xml version="1.0"?>
<score-partwise><part-list><score-part id="P1"/></part-list><part id="P1">
  <measure number="1">
    <attributes><divisions>1</divisions></attributes>
    <note><pitch><step>C</step><octave>4</octave></pitch></note>
    <note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration></note>
  </measure>
</part></score-partwise>`;
    const cleaned = sanitizeForOsmd(xml);
    expect(cleaned).toContain("<step>D</step>");
    expect(cleaned).not.toContain("<step>C</step>");
  });

  it("leaves grace notes alone even without <duration>", () => {
    const xml = `<?xml version="1.0"?>
<score-partwise><part-list><score-part id="P1"/></part-list><part id="P1">
  <measure number="1">
    <attributes><divisions>1</divisions></attributes>
    <note><grace/><pitch><step>C</step><octave>4</octave></pitch></note>
  </measure>
</part></score-partwise>`;
    const cleaned = sanitizeForOsmd(xml);
    expect(cleaned).toContain("<grace");
    expect(cleaned).toContain("<step>C</step>");
  });

  it("inserts empty measures for missing measure numbers across parts", () => {
    const xml = `<?xml version="1.0"?>
<score-partwise>
  <part-list><score-part id="P1"/><score-part id="P2"/></part-list>
  <part id="P1">
    <measure number="1"><note><rest/><duration>1</duration></note></measure>
    <measure number="3"><note><rest/><duration>1</duration></note></measure>
    <measure number="4"><note><rest/><duration>1</duration></note></measure>
  </part>
  <part id="P2">
    <measure number="1"><note><rest/><duration>1</duration></note></measure>
    <measure number="2"><note><rest/><duration>1</duration></note></measure>
  </part>
</score-partwise>`;

    const cleaned = sanitizeForOsmd(xml);
    const doc = new DOMParser().parseFromString(cleaned, "application/xml");
    const parts = Array.from(doc.getElementsByTagName("part"));
    const numbersPerPart = parts.map((p) =>
      Array.from(p.children)
        .filter((el) => el.tagName.toLowerCase() === "measure")
        .map((m) => Number.parseInt(m.getAttribute("number") ?? "", 10)),
    );

    expect(numbersPerPart[0]).toEqual([1, 3, 4]);
    expect(numbersPerPart[1]).toEqual([1, 2, 3, 4]);

    const part2Measure3 = Array.from(parts[1].children).find(
      (el) => el.tagName.toLowerCase() === "measure" && el.getAttribute("number") === "3",
    );
    const part2Measure4 = Array.from(parts[1].children).find(
      (el) => el.tagName.toLowerCase() === "measure" && el.getAttribute("number") === "4",
    );
    expect(part2Measure3?.getElementsByTagName("rest").length).toBe(1);
    expect(part2Measure4?.getElementsByTagName("rest").length).toBe(1);
    expect(part2Measure3?.getElementsByTagName("duration")[0]?.textContent).toBe("1");
    expect(part2Measure4?.getElementsByTagName("duration")[0]?.textContent).toBe("1");
  });

  it("preserves measure numbers and inserts missing rests before later measures", () => {
    const xml = `<?xml version="1.0"?>
<score-partwise>
  <part-list><score-part id="P1"/><score-part id="P2"/></part-list>
  <part id="P1">
    <measure number="11"><note><rest/><duration>1</duration></note></measure>
    <measure number="12"><note><rest/><duration>1</duration></note></measure>
    <measure number="13"><note><rest/><duration>1</duration></note></measure>
    <measure number="14"><note><rest/><duration>1</duration></note></measure>
    <measure number="15"><note><rest/><duration>1</duration></note></measure>
  </part>
  <part id="P2">
    <measure number="11"><note><rest/><duration>1</duration></note></measure>
    <measure number="12"><note><rest/><duration>1</duration></note></measure>
    <measure number="15"><note><rest/><duration>1</duration></note></measure>
  </part>
</score-partwise>`;

    const cleaned = sanitizeForOsmd(xml);
    const doc = new DOMParser().parseFromString(cleaned, "application/xml");
    const part2 = doc.getElementsByTagName("part")[1];
    const part2Numbers = Array.from(part2.children)
      .filter((el) => el.tagName.toLowerCase() === "measure")
      .map((m) => Number.parseInt(m.getAttribute("number") ?? "", 10));

    expect(part2Numbers).toEqual([11, 12, 13, 14, 15]);

    const part2Measure13 = Array.from(part2.children).find(
      (el) => el.tagName.toLowerCase() === "measure" && el.getAttribute("number") === "13",
    );
    const part2Measure14 = Array.from(part2.children).find(
      (el) => el.tagName.toLowerCase() === "measure" && el.getAttribute("number") === "14",
    );
    expect(part2Measure13?.getElementsByTagName("rest").length).toBe(1);
    expect(part2Measure14?.getElementsByTagName("rest").length).toBe(1);
  });

  it("aligns non-reference part key signatures to the reference part", () => {
    const xml = `<?xml version="1.0"?>
<score-partwise>
  <part-list><score-part id="P1"/><score-part id="P2"/></part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <key><fifths>2</fifths><mode>major</mode></key>
      </attributes>
      <note><rest/><duration>1</duration></note>
    </measure>
    <measure number="2"><note><rest/><duration>1</duration></note></measure>
    <measure number="3"><note><rest/><duration>1</duration></note></measure>
  </part>
  <part id="P2">
    <measure number="1">
      <attributes>
        <key><fifths>0</fifths><mode>major</mode></key>
      </attributes>
      <note><rest/><duration>1</duration></note>
    </measure>
    <measure number="2"><note><rest/><duration>1</duration></note></measure>
    <measure number="3"><note><rest/><duration>1</duration></note></measure>
  </part>
</score-partwise>`;

    const cleaned = sanitizeForOsmd(xml);
    const doc = new DOMParser().parseFromString(cleaned, "application/xml");
    const part2 = doc.getElementsByTagName("part")[1];
    const part2Measures = Array.from(part2.children).filter(
      (el) => el.tagName.toLowerCase() === "measure",
    );

    const fifths = part2Measures.map(
      (m) =>
        m.getElementsByTagName("attributes")[0]
          ?.getElementsByTagName("key")[0]
          ?.getElementsByTagName("fifths")[0]
          ?.textContent ?? "",
    );
    expect(fifths).toEqual(["2", "2", "2"]);
  });

  it("drops natural accidentals introduced by missing key signatures after key alignment", () => {
    const xml = `<?xml version="1.0"?>
<score-partwise>
  <part-list><score-part id="P1"/><score-part id="P2"/></part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <key><fifths>2</fifths><mode>major</mode></key>
      </attributes>
      <note><pitch><step>F</step><octave>4</octave></pitch><duration>1</duration></note>
    </measure>
  </part>
  <part id="P2">
    <measure number="1">
      <attributes>
        <key><fifths>0</fifths><mode>major</mode></key>
      </attributes>
      <note>
        <pitch><step>F</step><alter>0</alter><octave>4</octave></pitch>
        <accidental>natural</accidental>
        <duration>1</duration>
      </note>
    </measure>
  </part>
</score-partwise>`;

    const cleaned = sanitizeForOsmd(xml);
    const doc = new DOMParser().parseFromString(cleaned, "application/xml");
    const note = doc.getElementsByTagName("part")[1].getElementsByTagName("note")[0];
    const accidental = note.getElementsByTagName("accidental")[0];
    const alter = note.getElementsByTagName("alter")[0];
    const keyFifths = doc
      .getElementsByTagName("part")[1]
      .getElementsByTagName("measure")[0]
      .getElementsByTagName("attributes")[0]
      .getElementsByTagName("key")[0]
      .getElementsByTagName("fifths")[0]?.textContent;

    expect(keyFifths).toBe("2");
    expect(accidental).toBeUndefined();
    expect(alter?.textContent).toBe("1");
  });

  it("drops contradictory naturals even when key signature is unchanged in later measures", () => {
    const xml = `<?xml version="1.0"?>
<score-partwise>
  <part-list><score-part id="P1"/><score-part id="P2"/></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><key><fifths>2</fifths><mode>major</mode></key></attributes>
      <note><pitch><step>F</step><octave>4</octave></pitch><duration>1</duration></note>
    </measure>
    <measure number="2">
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration></note>
    </measure>
  </part>
  <part id="P2">
    <measure number="1">
      <attributes><key><fifths>2</fifths><mode>major</mode></key></attributes>
      <note>
        <pitch><step>F</step><alter>0</alter><octave>4</octave></pitch>
        <accidental>natural</accidental>
        <duration>1</duration>
      </note>
    </measure>
    <measure number="2">
      <note>
        <pitch><step>C</step><alter>0</alter><octave>5</octave></pitch>
        <accidental>natural</accidental>
        <duration>1</duration>
      </note>
    </measure>
  </part>
</score-partwise>`;

    const cleaned = sanitizeForOsmd(xml);
    const doc = new DOMParser().parseFromString(cleaned, "application/xml");
    const part2 = doc.getElementsByTagName("part")[1];
    const measure2 = part2.getElementsByTagName("measure")[1];
    const note = measure2.getElementsByTagName("note")[0];
    const accidental = note.getElementsByTagName("accidental")[0];
    const alter = note.getElementsByTagName("alter")[0];

    expect(accidental).toBeUndefined();
    expect(alter?.textContent).toBe("1");
  });

  it("prefers the part with stronger key metadata as alignment reference", () => {
    const xml = `<?xml version="1.0"?>
<score-partwise>
  <part-list><score-part id="P1"/><score-part id="P2"/></part-list>
  <part id="P1">
    <measure number="1"><note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration></note></measure>
    <measure number="2"><note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration></note></measure>
    <measure number="3"><note><pitch><step>E</step><octave>4</octave></pitch><duration>1</duration></note></measure>
  </part>
  <part id="P2">
    <measure number="1">
      <attributes><key><fifths>2</fifths><mode>major</mode></key></attributes>
      <note><pitch><step>F</step><octave>4</octave></pitch><duration>1</duration></note>
    </measure>
    <measure number="2"><note><pitch><step>G</step><octave>4</octave></pitch><duration>1</duration></note></measure>
  </part>
</score-partwise>`;

    const cleaned = sanitizeForOsmd(xml);
    const doc = new DOMParser().parseFromString(cleaned, "application/xml");
    const part1 = doc.getElementsByTagName("part")[0];
    const part1Measure1Fifths = part1
      .getElementsByTagName("measure")[0]
      .getElementsByTagName("attributes")[0]
      ?.getElementsByTagName("key")[0]
      ?.getElementsByTagName("fifths")[0]?.textContent;

    expect(part1Measure1Fifths).toBe("2");
  });
});
