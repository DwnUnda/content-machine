from __future__ import annotations

from datetime import datetime
from enum import StrEnum
import re
from urllib.parse import urlparse

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ArticleJobStatus(StrEnum):
    NEW = "New"
    RESEARCHING = "Researching"
    RESEARCH_COMPLETE = "Research complete"
    BRIEF_READY = "Brief ready"
    DRAFTING = "Drafting"
    DRAFT_COMPLETE = "Draft complete"
    QA_RUNNING = "QA running"
    QA_FAILED = "QA failed"
    READY_FOR_REVIEW = "Ready for review"
    EXPORTED_TO_WORDPRESS = "Exported to WordPress"
    ARCHIVED = "Archived"


class PostType(StrEnum):
    INFORMATIONAL_BLOG = "informational_blog"
    MONEY_POST = "money_post"
    SINGLE_PRODUCT_REVIEW = "single_product_review"
    PRODUCT_COMPARISON = "product_comparison"
    BEST_X_FOR_Y = "best_x_for_y"


class ContentCluster(Base, TimestampMixin):
    __tablename__ = "content_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    target_url_slug: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    article_jobs: Mapped[list["ArticleJob"]] = relationship(back_populates="content_cluster")


class ArticleJob(Base, TimestampMixin):
    __tablename__ = "article_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    primary_keyword: Mapped[str] = mapped_column(String(255), index=True)
    post_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(100), default=ArticleJobStatus.NEW.value, index=True)
    target_audience: Mapped[str | None] = mapped_column(String(255))
    australian_angle: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    cluster_id: Mapped[int | None] = mapped_column(ForeignKey("content_clusters.id"))
    review_override: Mapped[bool] = mapped_column(Boolean, default=False)
    current_qa_score: Mapped[float | None] = mapped_column(Float)

    content_cluster: Mapped[ContentCluster | None] = relationship(back_populates="article_jobs")
    serp_results: Mapped[list["SerpResult"]] = relationship(back_populates="article_job")
    keyword_research: Mapped[list["KeywordResearch"]] = relationship(back_populates="article_job")
    competitor_pages: Mapped[list["CompetitorPage"]] = relationship(back_populates="article_job")
    sources: Mapped[list["Source"]] = relationship(back_populates="article_job")
    briefs: Mapped[list["ArticleBrief"]] = relationship(back_populates="article_job")
    drafts: Mapped[list["ArticleDraft"]] = relationship(back_populates="article_job")
    qa_reports: Mapped[list["QaReport"]] = relationship(back_populates="article_job")
    wordpress_exports: Mapped[list["WordPressExport"]] = relationship(back_populates="article_job")
    internal_links: Mapped[list["InternalLink"]] = relationship(back_populates="article_job")
    app_logs: Mapped[list["AppLog"]] = relationship(back_populates="article_job")
    workflow_runs: Mapped[list["WorkflowRun"]] = relationship(back_populates="article_job")
    article_product_links: Mapped[list["ArticleJobProduct"]] = relationship(back_populates="article_job")
    product_candidates: Mapped[list["ProductCandidate"]] = relationship(back_populates="article_job")

    @property
    def local_export_path(self) -> str:
        from app.core.config import COMPLETED_ARTICLES_DIR

        slug = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-") or f"article-{self.id}"
        return str((COMPLETED_ARTICLES_DIR / "articles" / f"article-{self.id}-{slug}").resolve())


class SerpResult(Base, TimestampMixin):
    __tablename__ = "serp_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_job_id: Mapped[int] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    keyword: Mapped[str] = mapped_column(String(255))
    position: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(String(1000))
    domain: Mapped[str | None] = mapped_column(String(255))
    snippet: Mapped[str | None] = mapped_column(Text)
    result_type: Mapped[str | None] = mapped_column(String(100))
    source_payload: Mapped[dict | None] = mapped_column(JSON)

    article_job: Mapped[ArticleJob] = relationship(back_populates="serp_results")


class KeywordResearch(Base, TimestampMixin):
    __tablename__ = "keyword_research"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_job_id: Mapped[int] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    keyword: Mapped[str] = mapped_column(String(255))
    intent: Mapped[str | None] = mapped_column(String(100))
    search_volume: Mapped[int | None] = mapped_column(Integer)
    difficulty: Mapped[float | None] = mapped_column(Float)
    cpc: Mapped[float | None] = mapped_column(Float)
    competition: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    source_payload: Mapped[dict | None] = mapped_column(JSON)

    article_job: Mapped[ArticleJob] = relationship(back_populates="keyword_research")


class CompetitorPage(Base, TimestampMixin):
    __tablename__ = "competitor_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_job_id: Mapped[int] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    serp_result_id: Mapped[int | None] = mapped_column(ForeignKey("serp_results.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1000))
    domain: Mapped[str | None] = mapped_column(String(255))
    meta_description: Mapped[str | None] = mapped_column(Text)
    h1: Mapped[str | None] = mapped_column(Text)
    h2_list: Mapped[list | None] = mapped_column(JSON)
    h3_list: Mapped[list | None] = mapped_column(JSON)
    word_count_estimate: Mapped[int | None] = mapped_column(Integer)
    visible_text_extract: Mapped[str | None] = mapped_column(Text)
    detected_product_names: Mapped[list | None] = mapped_column(JSON)
    tables_count: Mapped[int | None] = mapped_column(Integer)
    faq_headings: Mapped[list | None] = mapped_column(JSON)
    affiliate_indicators: Mapped[list | None] = mapped_column(JSON)
    australian_relevance_signals: Mapped[list | None] = mapped_column(JSON)
    australian_relevance_score: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    page_type: Mapped[str | None] = mapped_column(String(100))
    extraction_method: Mapped[str | None] = mapped_column(String(50))
    extraction_status: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_extracted_data_json: Mapped[dict | None] = mapped_column(JSON)

    article_job: Mapped[ArticleJob] = relationship(back_populates="competitor_pages")
    serp_result: Mapped[SerpResult | None] = relationship()


class CompetitorAnalysisReport(Base, TimestampMixin):
    __tablename__ = "competitor_analysis_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_job_id: Mapped[int] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    dominant_intent: Mapped[str | None] = mapped_column(String(100))
    dominant_page_types_json: Mapped[dict | None] = mapped_column(JSON)
    common_headings_json: Mapped[list | None] = mapped_column(JSON)
    common_questions_json: Mapped[list | None] = mapped_column(JSON)
    repeated_products_json: Mapped[list | None] = mapped_column(JSON)
    competitor_gaps_json: Mapped[list | None] = mapped_column(JSON)
    australian_context_gaps_json: Mapped[list | None] = mapped_column(JSON)
    recommended_angle: Mapped[str | None] = mapped_column(Text)
    original_value_recommendations_json: Mapped[list | None] = mapped_column(JSON)
    suggested_support_articles_json: Mapped[list | None] = mapped_column(JSON)
    difficulty_estimate: Mapped[str | None] = mapped_column(String(50))
    raw_report_json: Mapped[dict | None] = mapped_column(JSON)


class Source(Base, TimestampMixin):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_job_id: Mapped[int | None] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(1000))
    source_type: Mapped[str] = mapped_column(String(100))
    publisher: Mapped[str | None] = mapped_column(String(255))
    trust_notes: Mapped[str | None] = mapped_column(Text)

    article_job: Mapped[ArticleJob | None] = relationship(back_populates="sources")
    product_links: Mapped[list["ProductSource"]] = relationship(back_populates="source")


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    brand: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(255))
    # Recommendation label within a buying guide, e.g. "Best Budget", "Best Premium".
    # Chosen per-topic during product discovery; drives the roundup structure in drafts.
    role: Mapped[str | None] = mapped_column(String(100))
    product_url: Mapped[str | None] = mapped_column(String(1000))
    personally_tested: Mapped[bool] = mapped_column(Boolean, default=False)
    model_number: Mapped[str | None] = mapped_column(String(255))
    retailer_domain: Mapped[str | None] = mapped_column(String(255))
    price_text: Mapped[str | None] = mapped_column(String(255))
    capacity_text: Mapped[str | None] = mapped_column(String(255))
    tank_size_text: Mapped[str | None] = mapped_column(String(255))
    noise_level_text: Mapped[str | None] = mapped_column(String(255))
    power_use_text: Mapped[str | None] = mapped_column(String(255))
    warranty_text: Mapped[str | None] = mapped_column(String(255))
    drainage_text: Mapped[str | None] = mapped_column(String(255))
    room_size_text: Mapped[str | None] = mapped_column(String(255))
    review_rating_text: Mapped[str | None] = mapped_column(String(255))
    review_count_text: Mapped[str | None] = mapped_column(String(255))
    description_snippet: Mapped[str | None] = mapped_column(Text)
    visible_specs_table: Mapped[dict | None] = mapped_column(JSON)
    confidence_level: Mapped[str | None] = mapped_column(String(50))
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    common_positives: Mapped[str | None] = mapped_column(Text)
    common_complaints: Mapped[str | None] = mapped_column(Text)
    who_should_buy: Mapped[str | None] = mapped_column(Text)
    who_should_avoid: Mapped[str | None] = mapped_column(Text)
    best_for: Mapped[str | None] = mapped_column(Text)
    bottom_line: Mapped[str | None] = mapped_column(Text)
    extraction_status: Mapped[str | None] = mapped_column(String(50))
    extraction_error: Mapped[str | None] = mapped_column(Text)
    raw_extracted_json: Mapped[dict | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)

    # Review-led product analysis layer. All additive and nullable. These let a
    # product card carry structured review/research signal so buying guides,
    # roundups, comparisons and review articles can be review-led rather than
    # spec-only. They never imply hands-on testing (see personally_tested).
    manufacturer_url: Mapped[str | None] = mapped_column(String(1000))
    retailer_urls: Mapped[list | None] = mapped_column(JSON)
    positive_review_patterns: Mapped[str | None] = mapped_column(Text)
    negative_review_patterns: Mapped[str | None] = mapped_column(Text)
    reliability_concerns: Mapped[str | None] = mapped_column(Text)
    key_specs: Mapped[list | None] = mapped_column(JSON)
    price_range_text: Mapped[str | None] = mapped_column(String(255))
    australian_availability: Mapped[str | None] = mapped_column(String(255))
    review_methodology_notes: Mapped[str | None] = mapped_column(Text)

    source_links: Mapped[list["ProductSource"]] = relationship(back_populates="product")
    reviews: Mapped[list["ProductReview"]] = relationship(back_populates="product")
    article_job_links: Mapped[list["ArticleJobProduct"]] = relationship(back_populates="product")

    @property
    def key_drawback(self) -> str | None:
        return self.common_complaints


class ArticleJobProduct(Base, TimestampMixin):
    __tablename__ = "article_job_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_job_id: Mapped[int] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    original_source_url: Mapped[str | None] = mapped_column(String(1000))
    cleaned_source_url: Mapped[str | None] = mapped_column(String(1000))
    source_type: Mapped[str] = mapped_column(String(100))
    extraction_status: Mapped[str | None] = mapped_column(String(50))
    extraction_error: Mapped[str | None] = mapped_column(Text)
    raw_extracted_json: Mapped[dict | None] = mapped_column(JSON)

    article_job: Mapped[ArticleJob] = relationship(back_populates="article_product_links")
    product: Mapped[Product | None] = relationship(back_populates="article_job_links")

    @property
    def retailer(self) -> str | None:
        if self.product and self.product.retailer_domain:
            return self.product.retailer_domain
        source = self.cleaned_source_url or self.source_url
        if not source:
            return None
        return urlparse(source).netloc or None

    @property
    def key_drawback(self) -> str | None:
        if self.product:
            return self.product.common_complaints
        return None

    @property
    def draft_blocking_missing_fields(self) -> list[str]:
        product = self.product
        if not product:
            return [
                "missing product card",
                "missing product name",
                "missing brand or retailer",
                "missing best for",
                "missing key drawback",
            ]

        def missing(value: str | None) -> bool:
            return value is None or not str(value).strip() or str(value).strip() == "Not confirmed"

        items: list[str] = []
        if missing(product.name):
            items.append("missing product name")
        if missing(product.brand) and missing(product.retailer_domain):
            items.append("missing brand or retailer")
        if missing(product.best_for):
            items.append("missing best for")
        if missing(product.common_complaints):
            items.append("missing key drawback")
        return items

    @property
    def missing_fields(self) -> list[str]:
        product = self.product
        if not product:
            return [
                "missing product card",
                "missing product name",
                "missing brand or retailer",
                "missing best for",
                "missing key drawback",
                "missing who should buy",
                "missing who should avoid",
            ]

        def missing(value: str | None) -> bool:
            return value is None or not str(value).strip() or str(value).strip() == "Not confirmed"

        items: list[str] = []
        if missing(product.name):
            items.append("missing product name")
        if missing(product.brand) and missing(product.retailer_domain):
            items.append("missing brand or retailer")
        if missing(product.best_for):
            items.append("missing best for")
        if missing(product.common_complaints):
            items.append("missing key drawback")
        if missing(product.who_should_buy):
            items.append("missing who should buy")
        if missing(product.who_should_avoid):
            items.append("missing who should avoid")
        return items

    def _raw(self) -> dict:
        return self.raw_extracted_json if isinstance(self.raw_extracted_json, dict) else {}

    @property
    def needs_review(self) -> bool:
        return bool(self._raw().get("needs_review"))

    @property
    def draft_ready_approved(self) -> bool:
        return bool(self._raw().get("draft_ready_approved"))

    @property
    def inferred_clues(self) -> dict:
        clues = self._raw().get("inferred_clues")
        return clues if isinstance(clues, dict) else {}

    @property
    def inferred_name(self) -> str | None:
        return self.inferred_clues.get("inferred_name")

    @property
    def extraction_failure_reason(self) -> str | None:
        return self._raw().get("extraction_failure_reason") or (
            self.extraction_error if self.extraction_status == "extraction_failed" else None
        )

    @property
    def research_sources(self) -> list:
        sources = self._raw().get("research_sources")
        return sources if isinstance(sources, list) else []

    @property
    def affiliate_url(self) -> str | None:
        # Editor-only; kept separate from the original source URL. Nullable / not required.
        return self._raw().get("affiliate_url")

    @property
    def draft_ready(self) -> bool:
        # A card is draft-ready only when core fields are present AND a human has reviewed it.
        if self.draft_blocking_missing_fields:
            return False
        # Cards that came straight from a successful direct extraction stay draft-ready
        # (legacy behaviour). Cards that were researched or failed extraction require an
        # explicit human approval before they count.
        if self.extraction_status in {"extraction_failed", "researched_needs_review", "research_needed"}:
            return self.draft_ready_approved
        if self.needs_review and not self.draft_ready_approved:
            return False
        return True

    @property
    def readiness_status(self) -> str:
        if self.draft_ready:
            return "Draft ready"
        status = self.extraction_status or "pending"
        labels = {
            "pending": "Extraction pending",
            "extraction_failed": "Extraction failed - needs research",
            "research_needed": "Needs product research",
            "researched_needs_review": "Researched - needs review",
            "success": "Needs manual edit",
            "rejected": "Rejected",
        }
        return labels.get(status, "Needs manual edit")


class ProductCandidate(Base, TimestampMixin):
    __tablename__ = "product_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_job_id: Mapped[int] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(255), index=True)
    brand: Mapped[str | None] = mapped_column(String(255))
    model_number: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    source_domain: Mapped[str | None] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(100))
    reason_found: Mapped[str | None] = mapped_column(Text)
    found_count: Mapped[int] = mapped_column(Integer, default=1)
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    suggested_best_for: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="suggested", index=True)
    raw_json: Mapped[dict | None] = mapped_column(JSON)

    article_job: Mapped[ArticleJob] = relationship(back_populates="product_candidates")


class ProductSource(Base, TimestampMixin):
    __tablename__ = "product_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    evidence_notes: Mapped[str | None] = mapped_column(Text)

    product: Mapped[Product] = relationship(back_populates="source_links")
    source: Mapped[Source] = relationship(back_populates="product_links")


class ProductReview(Base, TimestampMixin):
    __tablename__ = "product_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    rating: Mapped[float | None] = mapped_column(Float)
    reviewer_name: Mapped[str | None] = mapped_column(String(255))
    review_text: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(1000))

    product: Mapped[Product] = relationship(back_populates="reviews")
    summaries: Mapped[list["ReviewSummary"]] = relationship(back_populates="product_review")


class ReviewSummary(Base, TimestampMixin):
    __tablename__ = "review_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_review_id: Mapped[int] = mapped_column(ForeignKey("product_reviews.id"), index=True)
    summary: Mapped[str] = mapped_column(Text)
    sentiment: Mapped[str | None] = mapped_column(String(100))

    product_review: Mapped[ProductReview] = relationship(back_populates="summaries")


class ArticleBrief(Base, TimestampMixin):
    __tablename__ = "article_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_job_id: Mapped[int] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    brief_markdown: Mapped[str | None] = mapped_column(Text)
    outline_json: Mapped[dict | None] = mapped_column(JSON)
    serp_intent_json: Mapped[dict | None] = mapped_column(JSON)

    article_job: Mapped[ArticleJob] = relationship(back_populates="briefs")


class WorkflowRun(Base, TimestampMixin):
    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_job_id: Mapped[int] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    workflow_mode: Mapped[str] = mapped_column(String(50))
    research_mode: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), index=True)
    current_step: Mapped[str | None] = mapped_column(String(100))
    summary_message: Mapped[str | None] = mapped_column(Text)

    article_job: Mapped[ArticleJob] = relationship(back_populates="workflow_runs")
    steps: Mapped[list["WorkflowRunStep"]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
    )


class WorkflowRunStep(Base, TimestampMixin):
    __tablename__ = "workflow_run_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    step_key: Mapped[str] = mapped_column(String(100), index=True)
    step_label: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), index=True)
    message: Mapped[str | None] = mapped_column(Text)

    workflow_run: Mapped[WorkflowRun] = relationship(back_populates="steps")


class ArticleDraft(Base, TimestampMixin):
    __tablename__ = "article_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_job_id: Mapped[int] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    stage: Mapped[str | None] = mapped_column(String(50), default="final")
    draft_markdown: Mapped[str | None] = mapped_column(Text)
    seo_title: Mapped[str | None] = mapped_column(String(255))
    meta_description: Mapped[str | None] = mapped_column(String(500))
    slug: Mapped[str | None] = mapped_column(String(255))
    excerpt: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(String(255))
    prompt_name: Mapped[str | None] = mapped_column(String(255))
    source_payload_json: Mapped[dict | None] = mapped_column(JSON)

    article_job: Mapped[ArticleJob] = relationship(back_populates="drafts")


class QaReport(Base, TimestampMixin):
    __tablename__ = "qa_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_job_id: Mapped[int] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    status: Mapped[str] = mapped_column(String(100))
    score: Mapped[float | None] = mapped_column(Float)
    passed_gate: Mapped[bool] = mapped_column(Boolean, default=False)
    findings_json: Mapped[dict | None] = mapped_column(JSON)
    summary: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(String(255))
    prompt_name: Mapped[str | None] = mapped_column(String(255))

    article_job: Mapped[ArticleJob] = relationship(back_populates="qa_reports")


class WordPressExport(Base, TimestampMixin):
    __tablename__ = "wordpress_exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_job_id: Mapped[int] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    export_status: Mapped[str] = mapped_column(String(100))
    wordpress_post_id: Mapped[str | None] = mapped_column(String(255))
    wordpress_status: Mapped[str] = mapped_column(String(50), default="draft")
    response_payload: Mapped[dict | None] = mapped_column(JSON)

    article_job: Mapped[ArticleJob] = relationship(back_populates="wordpress_exports")


class InternalLink(Base, TimestampMixin):
    __tablename__ = "internal_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_job_id: Mapped[int] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    anchor_text: Mapped[str] = mapped_column(String(255))
    target_url: Mapped[str] = mapped_column(String(1000))
    notes: Mapped[str | None] = mapped_column(Text)

    article_job: Mapped[ArticleJob] = relationship(back_populates="internal_links")


class CostLog(Base, TimestampMixin):
    __tablename__ = "cost_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(100), index=True)
    action: Mapped[str] = mapped_column(String(100))
    cost_amount: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(16))
    related_entity_type: Mapped[str | None] = mapped_column(String(100))
    related_entity_id: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)


class AppLog(Base, TimestampMixin):
    __tablename__ = "app_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[str] = mapped_column(String(20), default="INFO", index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    message: Mapped[str] = mapped_column(Text)
    article_job_id: Mapped[int | None] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)

    article_job: Mapped[ArticleJob | None] = relationship(back_populates="app_logs")


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    value: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100), index=True)


class StandardPostBatch(Base, TimestampMixin):
    """A bulk queue of standard (informational) article posts.

    Reuses the existing single-article workflow one keyword at a time. This is for
    standard informational posts only: no money pages and no product-card gating.
    """

    __tablename__ = "standard_post_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255))
    # pending | running | paused | complete | cancelled
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    # local_only | local_plus_draft (never publishes; draft only)
    wordpress_mode: Mapped[str] = mapped_column(String(50), default="local_only")
    summary_message: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list["StandardPostBatchItem"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="StandardPostBatchItem.position",
    )


class StandardPostBatchItem(Base, TimestampMixin):
    __tablename__ = "standard_post_batch_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("standard_post_batches.id"), index=True)
    keyword: Mapped[str] = mapped_column(String(500))
    slug: Mapped[str | None] = mapped_column(String(255), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # pending | running | complete | failed | skipped | cancelled
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    current_step: Mapped[str | None] = mapped_column(String(100))
    article_job_id: Mapped[int | None] = mapped_column(ForeignKey("article_jobs.id"), index=True)
    article_folder: Mapped[str | None] = mapped_column(String(1000))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    batch: Mapped[StandardPostBatch] = relationship(back_populates="items")
