from pydantic import BaseModel, Field

from app.schemas.common import TimestampedResponse


class SourceBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    url: str | None = None
    source_type: str
    publisher: str | None = None
    trust_notes: str | None = None
    article_job_id: int | None = None


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    title: str | None = None
    url: str | None = None
    source_type: str | None = None
    publisher: str | None = None
    trust_notes: str | None = None
    article_job_id: int | None = None


class SourceResponse(TimestampedResponse):
    title: str
    url: str | None = None
    source_type: str
    publisher: str | None = None
    trust_notes: str | None = None
    article_job_id: int | None = None

