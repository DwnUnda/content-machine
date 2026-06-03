from pydantic import BaseModel

from app.schemas.common import TimestampedResponse


class ArticleDraftResponse(TimestampedResponse):
    article_job_id: int
    version: int
    stage: str | None = None
    draft_markdown: str | None = None
    seo_title: str | None = None
    meta_description: str | None = None
    slug: str | None = None
    excerpt: str | None = None
    model_name: str | None = None
    prompt_name: str | None = None
    source_payload_json: dict | None = None


class ArticleDraftListResponse(BaseModel):
    items: list[ArticleDraftResponse]
