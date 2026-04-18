from pydantic import BaseModel, Field


class MeasureBox(BaseModel):
    index: int = Field(..., description="1-based measure number")
    page: int = Field(..., description="0-based page index")
    bbox: tuple[float, float, float, float] = Field(
        ..., description="x, y, width, height in PDF points"
    )


class AnalyzeResponse(BaseModel):
    music_xml: str
    accompaniment_part_id: str | None
    measures: list[MeasureBox]
    divisions: int
    tempo_bpm: float
    page_sizes: list[tuple[float, float]] = Field(
        default_factory=list,
        description="Width/height in PDF points per page",
    )
    warnings: list[str] = Field(default_factory=list)
