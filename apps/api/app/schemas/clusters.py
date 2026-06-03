from pydantic import BaseModel, Field

from app.schemas.common import TimestampedResponse


class ContentClusterBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    target_url_slug: str | None = None
    notes: str | None = None


class ContentClusterCreate(ContentClusterBase):
    pass


class ContentClusterUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    target_url_slug: str | None = None
    notes: str | None = None


class ContentClusterResponse(TimestampedResponse):
    name: str
    description: str | None = None
    target_url_slug: str | None = None
    notes: str | None = None

