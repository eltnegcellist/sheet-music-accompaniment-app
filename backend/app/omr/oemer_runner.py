from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree
from pdf2image import convert_from_path

logger = logging.getLogger("accompanist")


@dataclass
class OemerRunResult:
    music_xml: str | None
    warnings: list[str] = field(default_factory=list)
    used_command: str | None = None


def _read_musicxml(path: Path) -> str | None:
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".xml") and not name.startswith("META-INF"):
                    return zf.read(name).decode("utf-8", errors="replace")
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _render_pdf_pages(pdf_path: Path, image_dir: Path) -> tuple[list[Path], list[str]]:
    """Render PDF pages to PNG images for Oemer (which expects raster input)."""
    warnings: list[str] = []
    try:
        # 240 DPI keeps memory lower than 400 while preserving staffline fidelity.
        pages = convert_from_path(str(pdf_path), dpi=240)
    except Exception as exc:
        return [], [f"Failed to render PDF for Oemer: {exc}"]

    if not pages:
        return [], ["PDF had no renderable pages for Oemer."]

    image_paths: list[Path] = []
    for page_idx, page in enumerate(pages, start=1):
        image_path = image_dir / f"oemer_input_page{page_idx}.png"
        page.save(image_path, format="PNG")
        image_paths.append(image_path)
    warnings.append(f"Oemer will process {len(image_paths)} rendered page(s).")
    return image_paths, warnings


def _run_oemer_command(input_image: Path, output_dir: Path, cmd: list[str], env: dict[str, str]) -> tuple[str | None, str | None]:
    cmd_str = " ".join(cmd)
    logger.info("Running Oemer: %s", cmd_str)
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError:
        return None, f"Oemer command not found: {cmd_str}"
    except Exception as exc:
        return None, f"Oemer crashed while launching ({cmd_str}): {exc}"

    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip()
        detail = f" ({stderr[:240]})" if stderr else ""
        return None, f"Oemer exited with code {completed.returncode} using `{cmd_str}`{detail}"

    for pattern in ("*.musicxml", "*.xml", "*.mxl"):
        candidates = sorted(output_dir.rglob(pattern))
        if candidates:
            music_xml = _read_musicxml(candidates[0])
            if music_xml:
                logger.info("Oemer produced MusicXML: %s", candidates[0])
                return music_xml, None

    return None, f"Oemer succeeded but no MusicXML file was found ({cmd_str})"


def _merge_page_xmls(page_xmls: list[str]) -> str:
    if len(page_xmls) == 1:
        return page_xmls[0]

    roots = [etree.fromstring(xml.encode("utf-8")) for xml in page_xmls]
    base = roots[0]

    base_parts = base.findall("part")
    if not base_parts:
        return page_xmls[0]

    next_numbers = []
    for part in base_parts:
        measures = part.findall("measure")
        if measures:
            last_no = int(measures[-1].get("number", len(measures)))
        else:
            last_no = 0
        next_numbers.append(last_no + 1)

    for extra_root in roots[1:]:
        extra_parts = extra_root.findall("part")
        for idx, extra_part in enumerate(extra_parts):
            if idx >= len(base_parts):
                continue
            for m in extra_part.findall("measure"):
                cloned = etree.fromstring(etree.tostring(m))
                cloned.set("number", str(next_numbers[idx]))
                next_numbers[idx] += 1
                base_parts[idx].append(cloned)

    return etree.tostring(base, encoding="unicode")


def run_oemer(pdf_path: Path, output_dir: Path) -> OemerRunResult:
    """Run Oemer and return generated MusicXML content when available."""
    output_dir.mkdir(parents=True, exist_ok=True)

    entrypoint = shutil.which("oemer")
    if entrypoint is None:
        return OemerRunResult(
            music_xml=None,
            warnings=["Oemer CLI not found on PATH."],
        )

    with tempfile.TemporaryDirectory() as img_root:
        image_paths, warnings = _render_pdf_pages(pdf_path, Path(img_root))
        if not image_paths:
            logger.warning("Skipping Oemer: could not prepare input image")
            return OemerRunResult(music_xml=None, warnings=warnings)

        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = ""

        page_xmls: list[str] = []
        for page_idx, image_path in enumerate(image_paths, start=1):
            page_out = output_dir / f"page_{page_idx:03d}"
            page_out.mkdir(parents=True, exist_ok=True)
            cmd = [entrypoint, str(image_path), "-o", str(page_out)]
            xml_text, error = _run_oemer_command(image_path, page_out, cmd, env)
            if error is not None:
                warnings.append(f"Page {page_idx}: {error}")
                continue
            if xml_text is not None:
                page_xmls.append(xml_text)

        if not page_xmls:
            logger.warning("Skipping Oemer fusion; no usable output was produced")
            warnings.append("Oemer output unavailable for all pages.")
            return OemerRunResult(music_xml=None, warnings=warnings, used_command=entrypoint)

        if len(page_xmls) != len(image_paths):
            warnings.append(
                f"Oemer succeeded on {len(page_xmls)}/{len(image_paths)} pages; using partial merged output."
            )

        merged_xml = _merge_page_xmls(page_xmls)
        return OemerRunResult(
            music_xml=merged_xml,
            warnings=warnings,
            used_command=entrypoint,
        )
