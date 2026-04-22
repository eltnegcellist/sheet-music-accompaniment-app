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

  // Fill missing measure numbers per-part so OSMD keeps vertical alignment
  // across staves even when OMR drops full measures in one part.
  const parts = Array.from(doc.getElementsByTagName("part"));
  if (parts.length > 1) {
    const referencePart = pickReferencePart(parts);
    const canonicalNumbers = getDirectMeasureChildren(referencePart)
      .map((m) => Number.parseInt(m.getAttribute("number") ?? "", 10))
      .filter((n) => Number.isFinite(n));

    for (const part of parts) {
      if (part === referencePart) continue;
      const measures = getDirectMeasureChildren(part);
      let cursor = 0;

      for (const targetNum of canonicalNumbers) {
        let found = false;
        while (cursor < measures.length) {
          const num = Number.parseInt(measures[cursor].getAttribute("number") ?? "", 10);
          if (!Number.isFinite(num)) {
            cursor++;
            continue;
          }
          if (num === targetNum) {
            found = true;
            cursor++;
            break;
          }
          if (num < targetNum) {
            cursor++;
            continue;
          }
          break;
        }

        if (!found) {
          const emptyMeasure = createEmptyMeasure(doc, targetNum);
          if (cursor < measures.length) {
            part.insertBefore(emptyMeasure, measures[cursor]);
            measures.splice(cursor, 0, emptyMeasure);
          } else {
            part.appendChild(emptyMeasure);
            measures.push(emptyMeasure);
          }
          cursor++;
        }
      }
    }

    // Keep key signatures consistent with the best-recognized part.
    alignKeySignaturesToReference(referencePart, parts);
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


  // Strip <octave-shift> to prevent OSMD realValue crashes from malformed OMR output.
  const shifts = Array.from(doc.getElementsByTagName("octave-shift"));
  for (const s of shifts) {
    s.parentNode?.removeChild(s);
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

function getDirectMeasureChildren(part: Element): Element[] {
  return Array.from(part.children).filter(
    (el) => el.tagName.toLowerCase() === "measure",
  );
}

function pickReferencePart(parts: Element[]): Element {
  let ref = parts[0];
  for (const part of parts) {
    if (getDirectMeasureChildren(part).length > getDirectMeasureChildren(ref).length) {
      ref = part;
    }
  }
  return ref;
}

function createEmptyMeasure(doc: Document, number: number): Element {
  const emptyMeasure = doc.createElement("measure");
  emptyMeasure.setAttribute("number", String(number));
  const note = doc.createElement("note");
  const rest = doc.createElement("rest");
  const duration = doc.createElement("duration");
  duration.textContent = "1";
  note.appendChild(rest);
  note.appendChild(duration);
  emptyMeasure.appendChild(note);

  return emptyMeasure;
}

interface KeyState {
  fifths: string;
  mode: string | null;
}

function alignKeySignaturesToReference(referencePart: Element, parts: Element[]): void {
  const keyByMeasure = new Map<number, KeyState>();
  let currentKey: KeyState | null = null;
  for (const measure of getDirectMeasureChildren(referencePart)) {
    const measureNumber = Number.parseInt(measure.getAttribute("number") ?? "", 10);
    if (!Number.isFinite(measureNumber)) continue;
    const explicit = readExplicitKeyState(measure);
    if (explicit) currentKey = explicit;
    if (currentKey) keyByMeasure.set(measureNumber, currentKey);
  }

  for (const part of parts) {
    if (part === referencePart) continue;
    for (const measure of getDirectMeasureChildren(part)) {
      const measureNumber = Number.parseInt(measure.getAttribute("number") ?? "", 10);
      if (!Number.isFinite(measureNumber)) continue;
      const refKey = keyByMeasure.get(measureNumber);
      if (!refKey) continue;
      const beforeKey = readExplicitKeyState(measure);
      writeMeasureKeyState(measure, refKey);
      if (!sameKeyState(beforeKey, refKey)) {
        dropNaturalAccidentalsContradictingKey(measure, refKey);
      }
    }
  }
}

function readExplicitKeyState(measure: Element): KeyState | null {
  for (const child of Array.from(measure.children)) {
    if (child.tagName.toLowerCase() !== "attributes") continue;
    const keyEl = child.getElementsByTagName("key")[0];
    if (!keyEl) continue;
    const fifthsText = keyEl.getElementsByTagName("fifths")[0]?.textContent?.trim() ?? "";
    if (!fifthsText) continue;
    const modeText = keyEl.getElementsByTagName("mode")[0]?.textContent?.trim() ?? null;
    return { fifths: fifthsText, mode: modeText };
  }
  return null;
}

function writeMeasureKeyState(measure: Element, keyState: KeyState): void {
  const doc = measure.ownerDocument;
  if (!doc) return;
  let attributes = Array.from(measure.children).find(
    (child) => child.tagName.toLowerCase() === "attributes",
  );
  if (!attributes) {
    attributes = doc.createElement("attributes");
    measure.insertBefore(attributes, measure.firstChild);
  }

  let keyEl = attributes.getElementsByTagName("key")[0];
  if (!keyEl) {
    keyEl = doc.createElement("key");
    attributes.appendChild(keyEl);
  }

  let fifthsEl = keyEl.getElementsByTagName("fifths")[0];
  if (!fifthsEl) {
    fifthsEl = doc.createElement("fifths");
    keyEl.appendChild(fifthsEl);
  }
  fifthsEl.textContent = keyState.fifths;

  const existingMode = keyEl.getElementsByTagName("mode")[0];
  if (keyState.mode) {
    if (existingMode) existingMode.textContent = keyState.mode;
    else {
      const modeEl = doc.createElement("mode");
      modeEl.textContent = keyState.mode;
      keyEl.appendChild(modeEl);
    }
  } else if (existingMode) {
    keyEl.removeChild(existingMode);
  }
}

function sameKeyState(a: KeyState | null, b: KeyState): boolean {
  if (!a) return false;
  return a.fifths === b.fifths && (a.mode ?? "") === (b.mode ?? "");
}

function dropNaturalAccidentalsContradictingKey(measure: Element, keyState: KeyState): void {
  const fifths = Number.parseInt(keyState.fifths, 10);
  if (!Number.isFinite(fifths)) return;

  for (const note of Array.from(measure.getElementsByTagName("note"))) {
    if (note.getElementsByTagName("rest").length > 0) continue;
    const pitch = note.getElementsByTagName("pitch")[0];
    if (!pitch) continue;
    const step = (pitch.getElementsByTagName("step")[0]?.textContent ?? "").trim().toUpperCase();
    if (!step) continue;

    const impliedAlter = keyAlterForStep(fifths, step);
    if (impliedAlter === 0) continue;

    const accidentalEl = note.getElementsByTagName("accidental")[0];
    const accidentalText = accidentalEl?.textContent?.trim().toLowerCase() ?? "";
    const alterEl = pitch.getElementsByTagName("alter")[0];
    const alterValue = alterEl ? Number.parseFloat(alterEl.textContent ?? "") : null;
    const hasExplicitChromaticAlter = alterValue !== null && Number.isFinite(alterValue) && alterValue !== 0;
    const marksNatural = accidentalText === "natural" || alterValue === 0;

    if (marksNatural && !hasExplicitChromaticAlter) {
      if (accidentalText === "natural" && accidentalEl?.parentNode) {
        accidentalEl.parentNode.removeChild(accidentalEl);
      }
      if (alterEl && alterValue === 0) {
        alterEl.parentNode?.removeChild(alterEl);
      }
    }
  }
}

function keyAlterForStep(fifths: number, step: string): number {
  const sharpOrder = ["F", "C", "G", "D", "A", "E", "B"];
  const flatOrder = ["B", "E", "A", "D", "G", "C", "F"];
  if (fifths > 0) {
    const affected = new Set(sharpOrder.slice(0, Math.min(7, fifths)));
    return affected.has(step) ? 1 : 0;
  }
  if (fifths < 0) {
    const affected = new Set(flatOrder.slice(0, Math.min(7, Math.abs(fifths))));
    return affected.has(step) ? -1 : 0;
  }
  return 0;
}
