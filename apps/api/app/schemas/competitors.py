from pydantic import BaseModel

from app.schemas.common import TimestampedResponse


class CompetitorPageResponse(TimestampedResponse):
    article_job_id: int
    serp_result_id: int | None = None
    title: str | None = None
    url: str
    domain: str | None = None
    meta_description: str | None = None
    h1: str | None = None
    h2_list: list[str] | None = None
    h3_list: list[str] | None = None
    word_count_estimate: int | None = None
    visible_text_extract: str | None = None
    detected_product_names: list[str] | None = None
    tables_count: int | None = None
    faq_headings: list[str] | None = None
    affiliate_indicators: list[str] | None = None
    australian_relevance_signals: list[str] | None = None
    australian_relevance_score: int | None = None
    notes: str | None = None
    page_type: str | None = None
    extraction_method: str | None = None
    extraction_status: str | None = None
    error_message: str | None = None
    raw_extracted_data_json: dict | None = None


class CompetitorPagesListResponse(BaseModel):
    items: list[CompetitorPageResponse]


class CompetitorAnalysisReportResponse(TimestampedResponse):
    article_job_id: int
    dominant_intent: str | None = None
    dominant_page_types_json: dict | None = None
    common_headings_json: list[str] | None = None
    common_questions_json: list[str] | None = None
    repeated_products_json: list[str] | None = None
    competitor_gaps_json: list[str] | None = None
    australian_context_gaps_json: list[str] | None = None
    recommended_angle: str | None = None
    original_value_recommendations_json: list[str] | None = None
    suggested_support_articles_json: list[str] | None = None
    difficulty_estimate: str | None = None
    raw_report_json: dict | None = None

