/**
 * Expand a list of measures annotated with repeat / jump metadata into the
 * actual playback order.
 *
 * Supported constructs (MVP):
 *   - Forward / backward repeat barlines (`|:` / `:|`).
 *   - Volta brackets (`1.` / `2.` / etc.).
 *   - Da Capo (D.C.) and Dal Segno (D.S.) jumps, with optional `al fine` /
 *     `al coda` qualifiers.
 *   - Segno / Coda / Fine markers paired with the above jumps.
 *
 * The algorithm walks the measure list once, with a small amount of bounded
 * back-tracking on backward-repeats. Each forward-pass increments `pass` so
 * volta brackets pick the right ending. Jumps (D.C./D.S.) are taken at most
 * once each — once we've "consumed" the jump we set `dcDsTaken` so a measure
 * with both `:|` and `D.C. al fine` doesn't loop forever.
 */

export interface MeasureRepeatMeta {
  /** 1-based measure number from MusicXML. */
  index: number;
  /** True when the measure starts after a forward-repeat barline. */
  forwardRepeat: boolean;
  /** When set, the measure ends with a backward-repeat barline. The value is
   *  the number of times the section should be played in total (default 2). */
  backwardRepeat: number | null;
  /** Volta bracket numbers that begin at this measure. e.g. [1] for `1.`,
   *  [2,3] for combined `2./3.` brackets. */
  endingStarts: number[];
  /** Volta bracket numbers that close at this measure. */
  endingStops: number[];
  hasSegno: boolean;
  hasCoda: boolean;
  /** When set, this measure carries a Fine indication. After D.C./D.S. al
   *  Fine the playback should stop at this measure's end on the second pass. */
  fine: boolean;
  /** When set, this measure carries a "To Coda" indication. After D.S./D.C.
   *  al Coda we jump from here to the next `hasCoda` measure on the second
   *  pass. */
  toCoda: boolean;
  /** A jump that fires at the end of this measure on the *first* pass. */
  jump:
    | "da-capo"
    | "da-capo-al-fine"
    | "da-capo-al-coda"
    | "dal-segno"
    | "dal-segno-al-fine"
    | "dal-segno-al-coda"
    | null;
}

export interface ExpandedSlot {
  /** Position in the original input array (0-based). */
  rawIndex: number;
  /** 1-based measure number, copied from the source measure. */
  measureIndex: number;
  /** Which pass through this measure this slot represents (1 = first time). */
  pass: number;
}

interface ExpandState {
  measures: MeasureRepeatMeta[];
  output: ExpandedSlot[];
  // Map of "measure index" → which volta-bracket pass we're on. Each forward
  // repeat owns its own pass counter, but in practice MusicXML scores only
  // have one nested level so we track a single `pass` and let it grow.
  pass: number;
  // Backward-repeat indices that have already triggered a jump back. A
  // backward-repeat fires exactly (times-1) times; we re-enter the same
  // measure each time and increment the visit counter.
  backwardVisits: Map<number, number>;
  // Whether the active D.C./D.S. has already triggered. Prevents infinite
  // loops on second/third pass.
  dcDsTaken: boolean;
  // Once a jump is taken al-fine / al-coda, we set the corresponding flag and
  // honor it on the *next* pass through Fine / To-Coda markers.
  honourFine: boolean;
  honourToCoda: boolean;
  // 0-based index of the segno measure if seen during the playback so far.
  segnoIndex: number | null;
  // 0-based index of the coda measure if seen during the playback so far.
  codaIndex: number | null;
  // Safety: cap the total slots emitted so a malformed score can't generate
  // a multi-million-measure playback list.
  maxSlots: number;
}

const DEFAULT_MAX_SLOTS = 50_000;

export function expandRepeats(
  measures: MeasureRepeatMeta[],
  options: { maxSlots?: number } = {},
): ExpandedSlot[] {
  if (measures.length === 0) return [];
  // Pre-scan to find segno / coda landmarks. They need to be known on the
  // *first* pass through the score so a "to-coda" marker positioned earlier
  // than the coda mark itself can still find its target after a D.S./D.C.
  let segnoIndex: number | null = null;
  let codaIndex: number | null = null;
  for (let i = 0; i < measures.length; i++) {
    if (segnoIndex === null && measures[i].hasSegno) segnoIndex = i;
    if (codaIndex === null && measures[i].hasCoda) codaIndex = i;
  }

  const state: ExpandState = {
    measures,
    output: [],
    pass: 1,
    backwardVisits: new Map(),
    dcDsTaken: false,
    honourFine: false,
    honourToCoda: false,
    segnoIndex,
    codaIndex,
    maxSlots: options.maxSlots ?? DEFAULT_MAX_SLOTS,
  };

  let pos = 0;
  // Track the most recent forward-repeat position so backward-repeats know
  // where to jump back to. Defaults to 0 (start of piece) when no explicit
  // forward-repeat is present.
  let forwardAnchor = 0;

  while (pos < measures.length) {
    if (state.output.length >= state.maxSlots) {
      // Truncate gracefully — better to play a long-but-finite version than
      // hang the audio engine.
      break;
    }
    const m = measures[pos];

    // Update forward anchor as we cross repeat starts. The anchor moves when
    // we *enter* the measure on a fresh pass; subsequent revisits don't shift
    // it (otherwise nested repeats would never resolve).
    if (m.forwardRepeat) {
      forwardAnchor = pos;
    }

    // Volta-bracket selection: skip the measure (and the rest of the bracket
    // it belongs to) when its ending numbers don't include the current pass.
    if (m.endingStarts.length > 0 && !m.endingStarts.includes(state.pass)) {
      const skipTo = findEndingClose(measures, pos);
      pos = skipTo;
      continue;
    }

    // Honour "al fine" — when a D.C./D.S. al fine has fired we stop at the
    // first Fine we encounter.
    if (state.honourFine && m.fine) {
      // Emit this measure, then halt.
      state.output.push({
        rawIndex: pos,
        measureIndex: m.index,
        pass: state.pass,
      });
      break;
    }

    // Honour "al coda" — when a D.C./D.S. al coda has fired, jump from the
    // To-Coda marker to the Coda marker.
    if (
      state.honourToCoda &&
      m.toCoda &&
      state.codaIndex !== null &&
      state.codaIndex > pos
    ) {
      state.output.push({
        rawIndex: pos,
        measureIndex: m.index,
        pass: state.pass,
      });
      pos = state.codaIndex;
      continue;
    }

    // Emit the measure.
    state.output.push({
      rawIndex: pos,
      measureIndex: m.index,
      pass: state.pass,
    });

    // Decide what to do at the *end* of this measure.
    if (m.backwardRepeat !== null) {
      const visits = state.backwardVisits.get(pos) ?? 0;
      const remaining = m.backwardRepeat - 1 - visits;
      if (remaining > 0) {
        state.backwardVisits.set(pos, visits + 1);
        state.pass += 1;
        pos = forwardAnchor;
        continue;
      }
      // Repeat exhausted; reset pass for any later forward-repeat region.
      state.pass = 1;
    }

    if (m.jump !== null && !state.dcDsTaken) {
      state.dcDsTaken = true;
      state.pass = state.pass + 1;
      switch (m.jump) {
        case "da-capo":
          pos = 0;
          continue;
        case "da-capo-al-fine":
          state.honourFine = true;
          pos = 0;
          continue;
        case "da-capo-al-coda":
          state.honourToCoda = true;
          pos = 0;
          continue;
        case "dal-segno":
          pos = state.segnoIndex ?? 0;
          continue;
        case "dal-segno-al-fine":
          state.honourFine = true;
          pos = state.segnoIndex ?? 0;
          continue;
        case "dal-segno-al-coda":
          state.honourToCoda = true;
          pos = state.segnoIndex ?? 0;
          continue;
      }
    }

    pos += 1;
  }
  return state.output;
}

function findEndingClose(
  measures: MeasureRepeatMeta[],
  start: number,
): number {
  // Walk forward until the bracket that started at `start` is fully closed.
  // For single-measure brackets (a measure that has both ending starts and
  // stops, common with `1.,2.` engravings) the depth oscillates back to 0
  // immediately, so we return the very next index. The caller is expected to
  // re-evaluate that index — it may be the start of a sibling bracket.
  let depth = 0;
  let i = start;
  while (i < measures.length) {
    const m = measures[i];
    depth += m.endingStarts.length;
    depth -= m.endingStops.length;
    i += 1;
    if (depth <= 0) return i;
  }
  return measures.length;
}
