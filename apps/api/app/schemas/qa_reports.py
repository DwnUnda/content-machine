from pydantic import BaseModel

from app.schemas.common import TimestampedResponse


class QaReportResponse(TimestampedResponse):
    article_job_id: int
    status: str
    score: float | None = None
    passed_gate: bool = False
    findings_json: dict | None = None
    summary: str | None = None
    model_name: str | None = None
    prompt_name: str | None = None


class QaReportListResponse(BaseModel):
    items: list[QaReportResponse]
