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
    warnings: list[str] = field(default_factory=list)


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
    # Keep the CLI to the minimum set that was known to work: adding
    # `-transcribe` or `-save` alongside `-export` has been observed to
    # trigger NullPointerExceptions in Voices.refineScore / Book.reduceScores
    # on some scores — including PDFs that parse cleanly with `-export`
    # alone. `-export` internally transcribes and writes MusicXML, which
    # is all we strictly need.
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

    The output directory is created if missing. Audiveris output is streamed
    to the logger so operators can follow progress on long scores (a ~30 page
    sonata can take 20+ minutes).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = _audiveris_command(pdf_path, output_dir)
    logger.info("Running Audiveris: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise AudiverisError(str(exc)) from exc

    assert proc.stdout is not None
    tail: list[str] = []
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                logger.info("audiveris: %s", line)
                tail.append(line)
                if len(tail) > 50:
                    tail.pop(0)
        returncode = proc.wait(timeout=1800)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        raise AudiverisError("Audiveris timed out after 30 minutes") from exc

    warnings: list[str] = []
    if returncode != 0:
        # Audiveris refuses the book-level export when any sheet's transcription
        # failed. That doesn't mean all sheets failed — per-sheet .mxl files may
        # still be on disk. Try to salvage them before giving up.
        warnings.append(
            f"Audiveris exited with code {returncode}. Using any partial output "
            "that was saved before the failure. See backend logs for details."
        )
        logger.warning(
            "Audiveris non-zero exit (%s); attempting to salvage partial output."
            " Last lines:\n%s",
            returncode,
            "\n".join(tail[-20:]),
        )

    mxl_path = _find_best_musicxml(output_dir)
    if mxl_path is None:
        # No MusicXML at all — we truly have nothing to play. Surface the
        # Audiveris error rather than a silent empty response.
        raise AudiverisError(
            f"Audiveris produced no MusicXML output (exit {returncode}). "
            "Last output:\n" + "\n".join(tail[-20:])
        )

    music_xml = _read_musicxml(mxl_path)

    omr_path = _find_first(output_dir, ("*.omr",))
    measures: list[MeasureLayout] = []
    page_sizes: list[tuple[float, float]] = []
    if omr_path is not None:
        measures, page_sizes = parse_omr_project(omr_path)
    else:
        logger.warning("No .omr project file found; measure highlights disabled")
        warnings.append(
            "Audiveris did not save a project file; measure highlights disabled."
        )

    return OmrResult(
        music_xml=music_xml,
        measures=measures,
        page_sizes=page_sizes,
        warnings=warnings,
    )


def _find_first(directory: Path, patterns: tuple[str, ...]) -> Path | None:
    for pattern in patterns:
        for path in sorted(directory.rglob(pattern)):
            return path
    return None


def _find_best_musicxml(directory: Path) -> Path | None:
    """Pick the most complete MusicXML candidate from Audiveris output.

    Audiveris often emits both score-level and sheet-level files; taking the
    lexicographically first path can accidentally choose a partial sheet file.
    Prefer non-sheet names and larger files, then fall back deterministically.
    """
    candidates: list[Path] = []
    for pattern in ("*.mxl", "*.xml"):
        candidates.extend(sorted(directory.rglob(pattern)))
    if not candidates:
        return None

    def rank(path: Path) -> tuple[int, int, str]:
        name = path.name.lower()
        looks_partial = int(("sheet" in name) or ("page" in name))
        size = path.stat().st_size if path.exists() else 0
        return (looks_partial, -size, str(path))

    return sorted(candidates, key=rank)[0]


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
