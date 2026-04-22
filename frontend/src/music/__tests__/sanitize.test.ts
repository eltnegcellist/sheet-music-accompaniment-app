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

    expect(numbersPerPart[0]).toEqual([1, 2, 3]);
    expect(numbersPerPart[1]).toEqual([1, 2, 3]);

    const part1Measure2 = Array.from(parts[0].children).find(
      (el) => el.tagName.toLowerCase() === "measure" && el.getAttribute("number") === "2",
    );
    const part2Measure3 = Array.from(parts[1].children).find(
      (el) => el.tagName.toLowerCase() === "measure" && el.getAttribute("number") === "3",
    );
    expect(part1Measure2?.getElementsByTagName("rest").length).toBe(1);
    expect(part2Measure3?.getElementsByTagName("rest").length).toBe(1);
    expect(part1Measure2?.getElementsByTagName("duration")[0]?.textContent).toBe("1");
    expect(part2Measure3?.getElementsByTagName("duration")[0]?.textContent).toBe("1");
  });
});
