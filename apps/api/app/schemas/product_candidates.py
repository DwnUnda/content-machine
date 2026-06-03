from pydantic import BaseModel

from app.schemas.common import TimestampedResponse
from app.schemas.product_research import ArticleJobProductResponse


class ProductCandidateResponse(TimestampedResponse):
    article_job_id: int
    product_name: str
    brand: str | None = None
    model_number: str | None = None
    source_url: str | None = None
    source_domain: str | None = None
    source_type: str
    reason_found: str | None = None
    found_count: int
    confidence_score: int | None = None
    suggested_best_for: str | None = None
    status: str
    raw_json: dict | None = None


class ProductCandidatesListResponse(BaseModel):
    items: list[ProductCandidateResponse]


class ConvertProductCandidateRequest(BaseModel):
    auto_extract: bool = True


class ProductCandidateConversionResponse(BaseModel):
    candidate: ProductCandidateResponse
    product_link: ArticleJobProductResponse
