"""Tiny homr 0.7 CLI stand-in used by unit tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    images = [
        Path(arg)
        for arg in sys.argv[1:]
        if not arg.startswith("--") and Path(arg).suffix.lower() == ".png"
    ]
    if not images:
        return 2

    measures = []
    for index, _image in enumerate(images, start=1):
        measures.append(
            "<measure number='" + str(index) + "'>"
            "<note><pitch><step>C</step><octave>4</octave></pitch>"
            "<duration>" + str(index) + "</duration></note>"
            "</measure>"
        )

    xml = (
        "<score-partwise>"
        "<part-list><score-part id='P1'/></part-list>"
        "<part id='P1'>"
        + "".join(measures)
        + "</part></score-partwise>"
    )
    output = images[0].with_name("merged_" + images[0].stem + ".musicxml")
    output.write_text(xml, encoding="utf-8")
    print(f"recognized {len(images)} page(s)")
    return int(os.environ.get("FAKE_HOMR_EXIT", "0"))


if __name__ == "__main__":
    raise SystemExit(main())
