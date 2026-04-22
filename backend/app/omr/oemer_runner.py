from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def run_oemer(pdf_path: Path, output_dir: Path) -> str | None:
    """Run Oemer and return generated MusicXML content when available."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["oemer", str(pdf_path), "-o", str(output_dir)]
    logger.info("Running Oemer: %s", " ".join(cmd))

    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        logger.warning("Oemer CLI not found on PATH; skipping Oemer fusion")
        return None
    except Exception:
        logger.exception("Unexpected error while running Oemer")
        return None

    if completed.returncode != 0:
        logger.warning(
            "Oemer failed (exit %s): %s",
            completed.returncode,
            completed.stderr.strip(),
        )
        return None

    for pattern in ("*.musicxml", "*.xml", "*.mxl"):
        candidates = sorted(output_dir.rglob(pattern))
        if candidates:
            path = candidates[0]
            if path.suffix.lower() == ".mxl":
                logger.warning("Oemer produced .mxl; skipping because parser expects XML")
                return None
            return path.read_text(encoding="utf-8", errors="replace")

    logger.warning("Oemer completed but produced no MusicXML output")
    return None
