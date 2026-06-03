from pydantic import BaseModel, HttpUrl

from app.schemas.common import TimestampedResponse
from app.schemas.products import ProductResponse


class ArticleJobProductSourceCreate(BaseModel):
    source_url: HttpUrl
    source_type: str


class ExtractProductRequest(BaseModel):
    product_source_id: int


class ArticleJobProductResponse(TimestampedResponse):
    article_job_id: int
    product_id: int | None = None
    source_url: str
    original_source_url: str | None = None
    cleaned_source_url: str | None = None
    source_type: str
    retailer: str | None = None
    key_drawback: str | None = None
    draft_ready: bool = False
    readiness_status: str
    missing_fields: list[str] = []
    extraction_status: str | None = None
    extraction_error: str | None = None
    needs_review: bool = False
    draft_ready_approved: bool = False
    inferred_name: str | None = None
    extraction_failure_reason: str | None = None
    research_sources: list = []
    affiliate_url: str | None = None
    raw_extracted_json: dict | None = None
    product: ProductResponse | None = None


class ArticleJobProductsListResponse(BaseModel):
    items: list[ArticleJobProductResponse]
