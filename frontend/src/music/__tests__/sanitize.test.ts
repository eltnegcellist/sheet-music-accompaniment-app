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
});
