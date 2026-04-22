from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

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


def _pdf_to_input_image(pdf_path: Path, image_dir: Path) -> tuple[Path | None, list[str]]:
    """Render PDF to an image for Oemer (which expects raster input)."""
    warnings: list[str] = []
    try:
        pages = convert_from_path(str(pdf_path), dpi=400)
    except Exception as exc:
        return None, [f"Failed to render PDF for Oemer: {exc}"]

    if not pages:
        return None, ["PDF had no renderable pages for Oemer."]

    if len(pages) > 1:
        warnings.append(
            "Oemer currently runs on a single rendered page; using page 1 only."
        )

    image_path = image_dir / "oemer_input_page1.png"
    pages[0].save(image_path, format="PNG")
    return image_path, warnings


def _candidate_commands(input_image: Path, output_dir: Path) -> list[list[str]]:
    entrypoint = shutil.which("oemer")
    commands: list[list[str]] = []
    if entrypoint is not None:
        commands.append([entrypoint, str(input_image), "-o", str(output_dir)])
    commands.append(["python3", "-m", "oemer", str(input_image), "-o", str(output_dir)])
    return commands


def run_oemer(pdf_path: Path, output_dir: Path) -> OemerRunResult:
    """Run Oemer and return generated MusicXML content when available."""
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as img_root:
        image_path, pre_warnings = _pdf_to_input_image(pdf_path, Path(img_root))
        warnings: list[str] = list(pre_warnings)
        if image_path is None:
            logger.warning("Skipping Oemer: could not prepare input image")
            return OemerRunResult(music_xml=None, warnings=warnings)

        commands = _candidate_commands(image_path, output_dir)
        # Avoid GPU provider initialization errors in CPU-only containers.
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = ""

        for cmd in commands:
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
                warnings.append(f"Oemer command not found: {cmd_str}")
                continue
            except Exception as exc:
                warnings.append(f"Oemer crashed while launching ({cmd_str}): {exc}")
                continue

            if completed.returncode != 0:
                stderr = completed.stderr.strip() or completed.stdout.strip()
                detail = f" ({stderr[:240]})" if stderr else ""
                warnings.append(
                    f"Oemer exited with code {completed.returncode} using `{cmd_str}`{detail}"
                )
                continue

            for pattern in ("*.musicxml", "*.xml", "*.mxl"):
                candidates = sorted(output_dir.rglob(pattern))
                if candidates:
                    music_xml = _read_musicxml(candidates[0])
                    if music_xml:
                        logger.info("Oemer produced MusicXML: %s", candidates[0])
                        return OemerRunResult(
                            music_xml=music_xml,
                            warnings=warnings,
                            used_command=cmd_str,
                        )

            warnings.append(f"Oemer succeeded but no MusicXML file was found ({cmd_str})")

    logger.warning("Skipping Oemer fusion; no usable output was produced")
    return OemerRunResult(music_xml=None, warnings=warnings)
