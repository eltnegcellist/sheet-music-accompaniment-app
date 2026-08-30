"""Run the homr CLI and normalize its per-page MusicXML output.

homr 0.7 accepts images rather than PDFs. To keep peak memory bounded on
consumer Macs, this adapter rasterizes one PDF page at a time, then starts a
single homr process for the image directory. Pages are recognized sequentially
instead of starting multiple memory-heavy workers.
"""

from __future__ import annotations

import logging
import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path

from pdf2image import convert_from_path
from pypdf import PdfReader

from ..music.musicxml_concat import concat_musicxml
from ..pdf.splitter import count_pages
from .result import OmrError, OmrResult

logger = logging.getLogger(__name__)


class HomrError(OmrError):
    """Raised when homr fails to produce usable MusicXML."""


def _homr_command() -> list[str]:
    """Resolve homr from an override or from PATH."""
    explicit = os.environ.get("HOMR_COMMAND")
    if explicit:
        command = shlex.split(explicit)
        if command:
            return command

    executable = shutil.which("homr")
    if executable is None:
        raise HomrError(
            "homr command not found. Install the backend 'homr' extra or set "
            "HOMR_COMMAND to the homr launcher."
        )
    return [executable]


def _page_sizes(pdf_path: Path) -> list[tuple[float, float]]:
    try:
        reader = PdfReader(str(pdf_path), strict=False)
        return [
            (float(page.mediabox.width), float(page.mediabox.height))
            for page in reader.pages
        ]
    except Exception as exc:  # noqa: BLE001 - pypdf exposes varied parser errors
        logger.warning("homr: could not read PDF page sizes: %s", exc)
        return []


def _render_pdf_pages(
    pdf_path: Path,
    pages_dir: Path,
    *,
    page_count: int,
    dpi: int,
) -> list[Path]:
    """Rasterize one page per call so large scores do not accumulate in RAM."""
    pages_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    for page_number in range(1, page_count + 1):
        try:
            images = convert_from_path(
                str(pdf_path),
                dpi=dpi,
                first_page=page_number,
                last_page=page_number,
                fmt="png",
                thread_count=1,
                use_pdftocairo=True,
            )
        except Exception as exc:
            raise HomrError(
                f"Could not rasterize PDF page {page_number}: {exc}"
            ) from exc
        if not images:
            raise HomrError(f"PDF page {page_number} produced no image")
        page_path = pages_dir / f"page_{page_number:04d}.png"
        images[0].save(page_path, format="PNG")
        images[0].close()
        rendered.append(page_path)
    return rendered


def _should_use_coreml_encoder(coreml_encoder: bool | None, page_count: int) -> bool:
    if coreml_encoder is not None:
        return coreml_encoder
    return (
        platform.system() == "Darwin"
        and platform.machine() == "arm64"
        and page_count >= 4
    )


def _find_page_musicxml(output_dir: Path) -> list[Path]:
    candidates = sorted(output_dir.rglob("page_*.musicxml"))
    if candidates:
        return candidates
    # Keep compatibility with future homr versions that may use .xml.
    return sorted(output_dir.rglob("page_*.xml"))


def run_homr(
    pdf_path: Path,
    output_dir: Path,
    *,
    dpi: int = 300,
    timeout_sec: int = 3600,
    coreml_encoder: bool | None = None,
) -> OmrResult:
    """Recognize a PDF with homr and merge the page-level MusicXML files."""
    if dpi < 72:
        raise HomrError("homr raster DPI must be at least 72")

    output_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = output_dir / "pages"
    page_count = count_pages(pdf_path)
    page_sizes = _page_sizes(pdf_path)
    if page_count == 0:
        raise HomrError("Could not determine the PDF page count")

    _render_pdf_pages(
        pdf_path,
        pages_dir,
        page_count=page_count,
        dpi=dpi,
    )

    cmd = [*_homr_command(), str(pages_dir)]
    if _should_use_coreml_encoder(coreml_encoder, page_count):
        cmd.append("--coreml-encoder")

    logger.info("Running homr for %d page(s): %s", page_count, " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise HomrError(str(exc)) from exc

    try:
        stdout, _ = proc.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.communicate()
        raise HomrError(f"homr timed out after {timeout_sec} seconds") from exc

    lines = [line.rstrip() for line in stdout.splitlines() if line.strip()]
    for line in lines:
        logger.info("homr: %s", line)
    tail = lines[-50:]
    returncode = proc.returncode

    xml_paths = _find_page_musicxml(output_dir)
    if not xml_paths:
        raise HomrError(
            f"homr produced no MusicXML output (exit {returncode}). Last output:\n"
            + "\n".join(tail[-20:])
        )

    warnings = ["homrで解析しました。PDF連動小節ハイライトは現在利用できません。"]
    if returncode != 0:
        warnings.append(
            f"homr exited with code {returncode}; using saved partial output."
        )

    xml_pages = [
        path.read_text(encoding="utf-8", errors="replace") for path in xml_paths
    ]
    merged_xml = concat_musicxml(xml_pages, warnings=warnings)
    if not merged_xml.strip():
        raise HomrError("homr MusicXML output was empty")

    return OmrResult(
        music_xml=merged_xml,
        measures=[],
        page_sizes=page_sizes,
        warnings=warnings,
    )
