"""Tiny PyPI homr 0.7 CLI stand-in used by unit tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    positional = [Path(arg) for arg in sys.argv[1:] if not arg.startswith("--")]
    if len(positional) != 1 or not positional[0].is_dir():
        return 2

    pages_dir = positional[0]
    images = sorted(pages_dir.glob("page_*.png"))
    if not images:
        return 2

    for index, image in enumerate(images, start=1):
        xml = (
            "<score-partwise>"
            "<part-list><score-part id='P1'/></part-list>"
            "<part id='P1'><measure number='1'>"
            "<note><pitch><step>C</step><octave>4</octave></pitch>"
            f"<duration>{index}</duration></note>"
            "</measure></part>"
            "</score-partwise>"
        )
        image.with_suffix(".musicxml").write_text(xml, encoding="utf-8")

    print(f"recognized {len(images)} page(s)")
    return int(os.environ.get("FAKE_HOMR_EXIT", "0"))


if __name__ == "__main__":
    raise SystemExit(main())
