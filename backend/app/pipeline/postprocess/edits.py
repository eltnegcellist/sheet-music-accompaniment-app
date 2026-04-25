"""Edit log for the postprocess phase.

Phase 3 plan (3-0): every edit applied to the score is recorded as one
event in `postprocess_edits.jsonl`. The log is the contract between
postprocess sub-stages and the evaluator (Phase 4 reads it for the
`edits_penalty` term and for report.md).

Event shape (stable, do NOT add fields without bumping a version):
    {
      "op":       <str: rest_insert | snap | delete | chord_merge | tie_extend | …>,
      "location": {"part": <part_id>, "measure": <int>, "voice": <int>, "beat": <float>},
      "before":   <free-form dict>,
      "after":    <free-form dict>,
      "reason":   <str: human-readable explanation>
    }
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator


@dataclass(frozen=True)
class EditLocation:
    part: str | None = None
    measure: int | None = None
    voice: int | None = None
    beat: float | None = None


@dataclass(frozen=True)
class EditEvent:
    op: str
    location: EditLocation
    reason: str
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        # Drop None location fields so the log stays compact and CI greps
        # don't need to special-case nulls.
        loc = {k: v for k, v in asdict(self.location).items() if v is not None}
        return {
            "op": self.op,
            "location": loc,
            "reason": self.reason,
            "before": dict(self.before),
            "after": dict(self.after),
        }


class EditLog:
    """In-memory + on-disk edit log.

    Events accumulate in memory so callers can use them for stage metrics
    (e.g. `len(log)` is `edits_penalty` numerator) and are flushed to a
    JSON Lines file on `flush()` so the evaluator can read them later.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._events: list[EditEvent] = []
        self._path = path

    def __iter__(self) -> Iterator[EditEvent]:
        return iter(self._events)

    def __len__(self) -> int:
        return len(self._events)

    def append(
        self,
        op: str,
        *,
        reason: str,
        location: EditLocation | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> EditEvent:
        ev = EditEvent(
            op=op,
            location=location or EditLocation(),
            reason=reason,
            before=before or {},
            after=after or {},
        )
        self._events.append(ev)
        return ev

    def extend(self, events: Iterable[EditEvent]) -> None:
        self._events.extend(events)

    def by_op(self) -> dict[str, int]:
        """Counts grouped by operation — used for postprocess metrics."""
        counts: dict[str, int] = {}
        for ev in self._events:
            counts[ev.op] = counts.get(ev.op, 0) + 1
        return counts

    def flush(self, path: Path | None = None) -> Path:
        target = path or self._path
        if target is None:
            raise ValueError("EditLog.flush requires a path")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as fh:
            for ev in self._events:
                fh.write(json.dumps(ev.to_dict(), ensure_ascii=False, sort_keys=True))
                fh.write("\n")
        return target
