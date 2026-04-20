/**
 * MusicXML sanitizer for OSMD.
 *
 * Audiveris occasionally emits MusicXML fragments that OSMD chokes on — the
 * most common failure surface is `Cannot read properties of undefined
 * (reading 'realValue')`, which fires when OSMD tries to read a
 * Fraction-valued property (beat position, duration, …) that never got
 * constructed because the source element was malformed. This module strips
 * the handful of elements known to cause that class of failure, leaving the
 * rest of the score intact.
 *
 * Specifically we remove:
 *   * <time> elements that don't have both <beats> and <beat-type> children
 *     with valid positive integers. OSMD needs these to build the measure
 *     Fraction, so a partial <time> makes it crash rather than defaulting.
 *   * <note> elements that have no <duration> (or a zero/negative duration)
 *     and are not grace notes. Zero-length notes can't be placed on the
 *     score timeline.
 *   * <attributes> blocks whose <divisions> is 0/missing — these break
 *     duration math for every subsequent note. We replace the text with
 *     "1" (a sane default) rather than dropping the element, so downstream
 *     measure numbers don't shift.
 *
 * The sanitizer is intentionally permissive: we only touch elements that
 * are demonstrably broken. Anything we don't recognize is left alone so
 * OSMD can still render it.
 */
export function sanitizeForOsmd(xml: string): string {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  if (doc.querySelector("parsererror")) {
    return xml; // If the XML itself is malformed, nothing we can do here.
  }

  // Strip incomplete <time> elements.
  const times = Array.from(doc.getElementsByTagName("time"));
  for (const t of times) {
    const beats = Number.parseInt(
      t.getElementsByTagName("beats")[0]?.textContent ?? "",
      10,
    );
    const beatType = Number.parseInt(
      t.getElementsByTagName("beat-type")[0]?.textContent ?? "",
      10,
    );
    if (
      !Number.isFinite(beats) ||
      beats <= 0 ||
      !Number.isFinite(beatType) ||
      beatType <= 0
    ) {
      t.parentNode?.removeChild(t);
    }
  }

  // Fix <divisions> = 0 / missing by defaulting to 1.
  const divs = Array.from(doc.getElementsByTagName("divisions"));
  for (const d of divs) {
    const v = Number.parseInt(d.textContent ?? "", 10);
    if (!Number.isFinite(v) || v <= 0) {
      d.textContent = "1";
    }
  }

  // Strip zero-duration non-grace notes.
  const notes = Array.from(doc.getElementsByTagName("note"));
  for (const n of notes) {
    if (n.getElementsByTagName("grace").length > 0) continue;
    const durEl = n.getElementsByTagName("duration")[0];
    if (!durEl) {
      // A note without duration will break OSMD's Fraction math.
      n.parentNode?.removeChild(n);
      continue;
    }
    const v = Number.parseInt(durEl.textContent ?? "", 10);
    if (!Number.isFinite(v) || v <= 0) {
      n.parentNode?.removeChild(n);
    }
  }

  return new XMLSerializer().serializeToString(doc);
}
