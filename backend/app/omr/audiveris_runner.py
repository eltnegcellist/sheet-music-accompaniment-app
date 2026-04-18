"""Wrap the Audiveris CLI to extract MusicXML and per-measure layout from a PDF.

Audiveris emits two interesting artifacts:
  * `<basename>.mxl` (or `.xml`)  : MusicXML score
  * `<basename>.omr`              : zipped project file (XML inside) with
                                    pixel-coordinate layout information

We need both: the MusicXML drives playback, the .omr file gives us measure
bounding boxes so the frontend can highlight the current measure on top of
the original PDF.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .layout_parser import MeasureLayout, parse_omr_project

logger = logging.getLogger(__name__)


class AudiverisError(RuntimeError):
    """Raised when Audiveris fails to produce expected output."""


@dataclass
class OmrResult:
    music_xml: str
    measures: list[MeasureLayout]
    page_sizes: list[tuple[float, float]] = field(default_factory=list)


def _audiveris_command(pdf_path: Path, output_dir: Path) -> list[str]:
    # The .deb installer puts the launcher on PATH; honor that first so we
    # don't hard-depend on a particular install layout.
    launcher = shutil.which("Audiveris")
    if launcher is None:
        home = Path(os.environ.get("AUDIVERIS_HOME", "/opt/Audiveris"))
        candidates = list(home.glob("**/bin/Audiveris"))
        if not candidates:
            raise AudiverisError(
                f"Audiveris launcher not found on PATH or under {home}. "
                "Install the Audiveris .deb or set AUDIVERIS_HOME."
            )
        launcher = str(candidates[0])
    return [
        launcher,
        "-batch",
        "-export",
        "-output",
        str(output_dir),
        str(pdf_path),
    ]


def run_audiveris(pdf_path: Path, output_dir: Path) -> OmrResult:
    """Run Audiveris and return MusicXML + measure layouts.

    The output directory is created if missing.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = _audiveris_command(pdf_path, output_dir)
    logger.info("Running Audiveris: %s", " ".join(cmd))
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError as exc:
        raise AudiverisError(str(exc)) from exc

    if completed.returncode != 0:
        raise AudiverisError(
            f"Audiveris exited {completed.returncode}: {completed.stderr.strip()}"
        )

    mxl_path = _find_first(output_dir, ("*.mxl", "*.xml"))
    if mxl_path is None:
        raise AudiverisError("Audiveris produced no MusicXML output")

    music_xml = _read_musicxml(mxl_path)

    omr_path = _find_first(output_dir, ("*.omr",))
    measures: list[MeasureLayout] = []
    page_sizes: list[tuple[float, float]] = []
    if omr_path is not None:
        measures, page_sizes = parse_omr_project(omr_path)
    else:
        logger.warning("No .omr project file found; measure highlights disabled")

    return OmrResult(music_xml=music_xml, measures=measures, page_sizes=page_sizes)


def _find_first(directory: Path, patterns: tuple[str, ...]) -> Path | None:
    for pattern in patterns:
        for path in sorted(directory.rglob(pattern)):
            return path
    return None


def _read_musicxml(path: Path) -> str:
    """Read MusicXML directly, or extract it from a compressed .mxl archive."""
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as zf:
            # MusicXML compressed format: META-INF/container.xml points to the root
            for name in zf.namelist():
                if name.lower().endswith(".xml") and not name.startswith("META-INF"):
                    return zf.read(name).decode("utf-8", errors="replace")
        raise AudiverisError(f"No MusicXML found inside {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def cleanup(output_dir: Path) -> None:
    """Best-effort cleanup helper for callers that manage their own temp dirs."""
    shutil.rmtree(output_dir, ignore_errors=True)
