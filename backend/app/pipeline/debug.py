"""Debug mode + structured event logging for the pipeline.

The plan requires JSON Lines events with stable fields so an operator can
reconstruct any failure from `job_id` alone. This module is the single
source of truth for that format.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, IO


def is_debug_enabled(params: dict | None = None) -> bool:
    """Debug mode is on when the env var or params explicitly opt in.

    Checking both lets ops force-enable in production for one job (env)
    while CI defaults to params-driven.
    """
    if os.environ.get("PIPELINE_DEBUG") == "1":
        return True
    if params is None:
        return False
    return bool(params.get("debug", {}).get("enabled", False))


@dataclass
class StructuredEvent:
    """A single JSON-Lines event.

    Required fields are spelled out as attributes so a typo at construction
    time fails fast rather than silently producing malformed log lines.
    """

    ts: str
    event: str
    job_id: str
    stage: str
    status: str
    page_id: str | None = None
    trial_id: str | None = None
    param_set_id: str | None = None
    duration_ms: int | None = None
    metrics: dict[str, Any] | None = None
    warnings: list[str] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {
            "ts": self.ts,
            "event": self.event,
            "job_id": self.job_id,
            "stage": self.stage,
            "status": self.status,
        }
        for k in (
            "page_id",
            "trial_id",
            "param_set_id",
            "duration_ms",
            "metrics",
            "warnings",
            "error",
        ):
            v = getattr(self, k)
            if v not in (None, [], {}):
                out[k] = v
        return out


class EventLogger:
    """Writes JSON Lines events to a file (and optionally to stdlib logging).

    Tests inject a `StringIO` so we don't pollute the filesystem.
    """

    def __init__(
        self,
        sink: IO[str] | None = None,
        path: Path | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if sink is None and path is None:
            raise ValueError("EventLogger needs sink or path")
        self._sink = sink
        self._path = path
        self._logger = logger

    def emit(self, event: StructuredEvent) -> None:
        line = json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True)
        if self._sink is not None:
            self._sink.write(line + "\n")
            self._sink.flush()
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        if self._logger is not None:
            self._logger.info("pipeline_event %s", line)


def now_iso() -> str:
    """UTC timestamp with millisecond precision and `Z` suffix.

    Centralised so every event in the system uses an identical format —
    aggregators/CI matchers don't have to deal with multiple variants.
    """
    t = time.time()
    millis = int((t - int(t)) * 1000)
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{millis:03d}Z"
