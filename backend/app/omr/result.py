"""Engine-neutral OMR result and error types."""

from __future__ import annotations

from dataclasses import dataclass, field

from .layout_parser import MeasureLayout


class OmrError(RuntimeError):
    """Raised when an OMR engine produces no usable score."""


@dataclass
class OmrResult:
    """Normalized result returned by every supported OMR engine."""

    music_xml: str
    measures: list[MeasureLayout]
    page_sizes: list[tuple[float, float]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
