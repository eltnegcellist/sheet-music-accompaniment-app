from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .music.accompaniment import find_accompaniment_part
from .music.merger import merge_layout_with_musicxml
from .music.parser import extract_divisions_and_tempo, list_measures_with_bbox
from .omr.audiveris_runner import AudiverisError, run_audiveris
from .schemas import AnalyzeResponse, MeasureBox

logger = logging.getLogger("accompanist")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="IMSLP Accompanist")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    pdf: UploadFile = File(...),
    music_xml: UploadFile | None = File(default=None),
) -> AnalyzeResponse:
    if pdf.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(400, f"Unexpected content-type: {pdf.content_type}")

    with tempfile.TemporaryDirectory() as tmp_root:
        tmp = Path(tmp_root)
        pdf_path = tmp / "input.pdf"
        pdf_path.write_bytes(await pdf.read())

        user_xml: str | None = None
        if music_xml is not None:
            user_xml = (await music_xml.read()).decode("utf-8", errors="replace")

        warnings: list[str] = []
        try:
            omr_result = run_audiveris(pdf_path, tmp / "out")
        except AudiverisError as exc:
            logger.exception("Audiveris failed")
            raise HTTPException(500, f"OMR failed: {exc}") from exc
        warnings.extend(omr_result.warnings)

        merged_xml = merge_layout_with_musicxml(
            omr_xml=omr_result.music_xml,
            user_xml=user_xml,
            warnings=warnings,
        )

        accompaniment_part_id = find_accompaniment_part(merged_xml)
        if accompaniment_part_id is None:
            warnings.append(
                "Could not auto-detect accompaniment (piano) part; "
                "falling back to last part."
            )

        divisions, tempo_bpm = extract_divisions_and_tempo(merged_xml)
        measures = [
            MeasureBox(index=m.index, page=m.page, bbox=m.bbox)
            for m in list_measures_with_bbox(omr_result, accompaniment_part_id)
        ]

        return AnalyzeResponse(
            music_xml=merged_xml,
            accompaniment_part_id=accompaniment_part_id,
            measures=measures,
            divisions=divisions,
            tempo_bpm=tempo_bpm,
            page_sizes=omr_result.page_sizes,
            warnings=warnings,
        )
