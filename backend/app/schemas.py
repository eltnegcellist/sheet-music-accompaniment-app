from pydantic import BaseModel, Field


class MeasureBox(BaseModel):
    index: int = Field(..., description="1-based measure number")
    page: int = Field(..., description="0-based page index")
    bbox: tuple[float, float, float, float] = Field(
        ..., description="x, y, width, height in PDF points"
    )


class TimeSignatureModel(BaseModel):
    beats: int
    beat_type: int


class AnalyzeResponse(BaseModel):
    music_xml: str
    score_title: str | None = None
    accompaniment_part_id: str | None
    solo_part_id: str | None = None
    measures: list[MeasureBox]
    divisions: int
    tempo_bpm: float
    tempo_source: str = Field(
        default="default",
        description="Which rule produced tempo_bpm: sound | metronome | word | ocr-word | default",
    )
    tempo_matched_word: str | None = Field(
        default=None,
        description="The specific tempo word matched (e.g. 'allegro') if source is word or ocr-word.",
    )
    tempo_candidates: list[str] = Field(
        default_factory=list,
        description="All <words>/<credit-words>/<rehearsal> texts found — useful for diagnosing why tempo detection missed a marking.",
    )
    time_signature: TimeSignatureModel | None = None
    page_sizes: list[tuple[float, float]] = Field(
        default_factory=list,
        description="Width/height in PDF points per page",
    )
    warnings: list[str] = Field(default_factory=list)
