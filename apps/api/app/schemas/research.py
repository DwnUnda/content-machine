from pydantic import BaseModel

from app.schemas.common import TimestampedResponse


class SerpResultResponse(TimestampedResponse):
    article_job_id: int
    keyword: str
    position: int | None = None
    title: str | None = None
    url: str | None = None
    domain: str | None = None
    snippet: str | None = None
    result_type: str | None = None
    source_payload: dict | None = None


class KeywordResearchResponse(TimestampedResponse):
    article_job_id: int
    keyword: str
    intent: str | None = None
    search_volume: int | None = None
    difficulty: float | None = None
    cpc: float | None = None
    competition: str | None = None
    source: str | None = None
    notes: str | None = None
    source_payload: dict | None = None


class SerpResultsListResponse(BaseModel):
    items: list[SerpResultResponse]


class KeywordResearchListResponse(BaseModel):
    items: list[KeywordResearchResponse]

