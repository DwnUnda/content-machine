from pydantic import BaseModel

from app.schemas.common import TimestampedResponse


class AppLogResponse(TimestampedResponse):
    level: str
    event_type: str
    message: str
    article_job_id: int | None = None
    metadata_json: dict | None = None


class AppLogListResponse(BaseModel):
    items: list[AppLogResponse]

