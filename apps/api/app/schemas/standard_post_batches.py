from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import TimestampedResponse


class StandardPostBatchItemResponse(TimestampedResponse):
    batch_id: int
    keyword: str
    slug: str | None = None
    position: int
    status: str
    current_step: str | None = None
    article_job_id: int | None = None
    article_folder: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class StandardPostBatchCounts(BaseModel):
    total: int = 0
    pending: int = 0
    running: int = 0
    complete: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: int = 0


class StandardPostBatchSummary(TimestampedResponse):
    name: str | None = None
    status: str
    wordpress_mode: str
    summary_message: str | None = None
    counts: StandardPostBatchCounts = StandardPostBatchCounts()
    is_running: bool = False


class StandardPostBatchDetail(StandardPostBatchSummary):
    items: list[StandardPostBatchItemResponse] = []


class StandardPostBatchCreate(BaseModel):
    keywords: str
    name: str | None = None
    # local_only (default) | local_plus_draft (draft only, never publishes)
    wordpress_mode: str = "local_only"
