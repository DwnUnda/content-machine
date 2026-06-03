from pydantic import BaseModel

from app.schemas.common import TimestampedResponse


class ArticleBriefResponse(TimestampedResponse):
    article_job_id: int
    version: int
    brief_markdown: str | None = None
    outline_json: dict | None = None


class ArticleBriefListResponse(BaseModel):
    items: list[ArticleBriefResponse]


class ArticleBriefUpdateRequest(BaseModel):
    brief_markdown: str
