"""Extract per-measure pixel coordinates from an Audiveris `.omr` project file.

The `.omr` file is a ZIP that contains a `book.xml` plus per-sheet XML files.
Each sheet XML lists `<MeasureStack>` (or `<measure>` elements depending on
Audiveris version) with `<bounds x="..." y="..." width="..." height="..."/>`.

We deliberately keep the parser tolerant: Audiveris XML schema has changed
between minor versions, so we walk the tree looking for elements whose tag
contains "Measure" and whose bounds attribute is present.
"""

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

logger = logging.getLogger(__name__)


@dataclass
class MeasureLayout:
    index: int  # 1-based measure number
    page: int  # 0-based page index
    bbox: tuple[float, float, float, float]  # x, y, width, height (image pixels)


def parse_omr_project(
    omr_path: Path,
) -> tuple[list[MeasureLayout], list[tuple[float, float]]]:
    """Return (measures, page_sizes) from an Audiveris project file."""
    measures: list[MeasureLayout] = []
    page_sizes: list[tuple[float, float]] = []

    with zipfile.ZipFile(omr_path) as zf:
        sheet_files = sorted(
            n for n in zf.namelist() if n.endswith(".xml") and "sheet" in n.lower()
        )
        if not sheet_files:
            sheet_files = sorted(n for n in zf.namelist() if n.endswith(".xml"))

        running_index = 0
        for page_idx, name in enumerate(sheet_files):
            data = zf.read(name)
            try:
                root = etree.fromstring(data)
            except etree.XMLSyntaxError as exc:
                logger.warning("Skipping malformed sheet XML %s: %s", name, exc)
                continue

            width, height = _read_page_size(root)
            if width and height:
                page_sizes.append((width, height))

            for measure_el in _iter_measures(root):
                bbox = _read_bbox(measure_el)
                if bbox is None:
                    continue
                running_index += 1
                explicit = measure_el.get("number") or measure_el.get("id")
                index = _safe_int(explicit, running_index)
                measures.append(
                    MeasureLayout(index=index, page=page_idx, bbox=bbox)
                )

    return measures, page_sizes


def _iter_measures(root: etree._Element):
    for el in root.iter():
        tag = etree.QName(el).localname
        if "Measure" in tag or tag == "measure":
            yield el


def _read_bbox(el: etree._Element) -> tuple[float, float, float, float] | None:
    # Audiveris uses both attribute style (<bounds x= y= w= h=/>) and child
    # element style depending on serialization. Handle both.
    bounds = el.find("bounds")
    if bounds is not None:
        attrs = bounds.attrib
    else:
        attrs = el.attrib

    try:
        x = float(attrs.get("x") or attrs.get("X") or "")
        y = float(attrs.get("y") or attrs.get("Y") or "")
        w = float(attrs.get("width") or attrs.get("w") or "")
        h = float(attrs.get("height") or attrs.get("h") or "")
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return (x, y, w, h)


def _read_page_size(root: etree._Element) -> tuple[float, float]:
    # Look for a sheet/page level <dimension width=... height=.../> element.
    for el in root.iter():
        tag = etree.QName(el).localname
        if tag.lower() in {"dimension", "size", "page"}:
            try:
                w = float(el.get("width") or "")
                h = float(el.get("height") or "")
            except (TypeError, ValueError):
                continue
            if w > 0 and h > 0:
                return (w, h)
    return (0.0, 0.0)


def _safe_int(value: str | None, fallback: int) -> int:
    if value is None:
        return fallback
    try:
        return int(value)
    except ValueError:
        return fallback
