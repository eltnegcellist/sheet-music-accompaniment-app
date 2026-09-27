"""Tiny homr CLI stand-in used by unit tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    directories = [Path(arg) for arg in sys.argv[1:] if not arg.startswith("--")]
    if not directories:
        return 2
    pages_dir = directories[0]
    for index, image in enumerate(sorted(pages_dir.glob("page_*.png")), start=1):
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
    print(f"recognized {len(list(pages_dir.glob('page_*.png')))} page(s)")
    return int(os.environ.get("FAKE_HOMR_EXIT", "0"))


if __name__ == "__main__":
    raise SystemExit(main())
