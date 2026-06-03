from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel, TimestampedResponse


class ArticleJobBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    primary_keyword: str = Field(min_length=1, max_length=255)
    post_type: str
    target_audience: str | None = None
    australian_angle: str | None = None
    notes: str | None = None
    cluster_id: int | None = None


class ArticleJobCreate(ArticleJobBase):
    pass


class ArticleJobUpdate(BaseModel):
    title: str | None = None
    primary_keyword: str | None = None
    post_type: str | None = None
    status: str | None = None
    target_audience: str | None = None
    australian_angle: str | None = None
    notes: str | None = None
    cluster_id: int | None = None


class ArticleJobSummary(TimestampedResponse):
    title: str
    primary_keyword: str
    post_type: str
    status: str
    target_audience: str | None = None
    cluster_id: int | None = None
    review_override: bool = False
    current_qa_score: float | None = None


class RelatedRecord(ORMModel):
    id: int
    created_at: datetime
    updated_at: datetime


class ArticleJobDetail(ArticleJobSummary):
    australian_angle: str | None = None
    notes: str | None = None
    local_export_path: str | None = None
    serp_results: list[RelatedRecord] = []
    keyword_research: list[RelatedRecord] = []
    competitor_pages: list[RelatedRecord] = []
    sources: list[RelatedRecord] = []
    briefs: list[RelatedRecord] = []
    drafts: list[RelatedRecord] = []
    qa_reports: list[RelatedRecord] = []
    wordpress_exports: list[RelatedRecord] = []
    internal_links: list[RelatedRecord] = []


class WorkflowActionResponse(BaseModel):
    action: str
    article_job_id: int
    status: str
    message: str
    next_step: str | None = None
