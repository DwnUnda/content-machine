"""initial foundation

Revision ID: 20260527_0001
Revises:
Create Date: 2026-05-27 16:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260527_0001"
down_revision = None
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("content_clusters", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(length=255), nullable=False), sa.Column("description", sa.Text()), sa.Column("target_url_slug", sa.String(length=255)), sa.Column("notes", sa.Text()), *_timestamps())
    op.create_index("ix_content_clusters_name", "content_clusters", ["name"], unique=True)
    op.create_table("article_jobs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("title", sa.String(length=255), nullable=False), sa.Column("primary_keyword", sa.String(length=255), nullable=False), sa.Column("article_type", sa.String(length=100), nullable=False), sa.Column("status", sa.String(length=100), nullable=False), sa.Column("target_audience", sa.String(length=255)), sa.Column("australian_angle", sa.Text()), sa.Column("notes", sa.Text()), sa.Column("cluster_id", sa.Integer(), sa.ForeignKey("content_clusters.id")), *_timestamps())
    op.create_index("ix_article_jobs_title", "article_jobs", ["title"], unique=False)
    op.create_index("ix_article_jobs_primary_keyword", "article_jobs", ["primary_keyword"], unique=False)
    op.create_index("ix_article_jobs_status", "article_jobs", ["status"], unique=False)
    op.create_table("products", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(length=255), nullable=False), sa.Column("brand", sa.String(length=255)), sa.Column("category", sa.String(length=255)), sa.Column("product_url", sa.String(length=1000)), sa.Column("personally_tested", sa.Boolean(), nullable=False, server_default=sa.text("0")), sa.Column("notes", sa.Text()), *_timestamps())
    op.create_index("ix_products_name", "products", ["name"], unique=False)
    op.create_table("sources", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id")), sa.Column("title", sa.String(length=255), nullable=False), sa.Column("url", sa.String(length=1000)), sa.Column("source_type", sa.String(length=100), nullable=False), sa.Column("publisher", sa.String(length=255)), sa.Column("trust_notes", sa.Text()), *_timestamps())
    op.create_index("ix_sources_article_job_id", "sources", ["article_job_id"], unique=False)
    op.create_table("serp_results", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id"), nullable=False), sa.Column("keyword", sa.String(length=255), nullable=False), sa.Column("position", sa.Integer()), sa.Column("title", sa.String(length=500)), sa.Column("url", sa.String(length=1000)), sa.Column("snippet", sa.Text()), sa.Column("source_payload", sa.JSON()), *_timestamps())
    op.create_index("ix_serp_results_article_job_id", "serp_results", ["article_job_id"], unique=False)
    op.create_table("keyword_research", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id"), nullable=False), sa.Column("keyword", sa.String(length=255), nullable=False), sa.Column("intent", sa.String(length=100)), sa.Column("search_volume", sa.Integer()), sa.Column("difficulty", sa.Float()), sa.Column("notes", sa.Text()), *_timestamps())
    op.create_index("ix_keyword_research_article_job_id", "keyword_research", ["article_job_id"], unique=False)
    op.create_table("competitor_pages", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id"), nullable=False), sa.Column("title", sa.String(length=500), nullable=False), sa.Column("url", sa.String(length=1000), nullable=False), sa.Column("notes", sa.Text()), sa.Column("page_type", sa.String(length=100)), *_timestamps())
    op.create_index("ix_competitor_pages_article_job_id", "competitor_pages", ["article_job_id"], unique=False)
    op.create_table("product_sources", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False), sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False), sa.Column("evidence_notes", sa.Text()), *_timestamps())
    op.create_index("ix_product_sources_product_id", "product_sources", ["product_id"], unique=False)
    op.create_index("ix_product_sources_source_id", "product_sources", ["source_id"], unique=False)
    op.create_table("product_reviews", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False), sa.Column("rating", sa.Float()), sa.Column("reviewer_name", sa.String(length=255)), sa.Column("review_text", sa.Text()), sa.Column("source_url", sa.String(length=1000)), *_timestamps())
    op.create_index("ix_product_reviews_product_id", "product_reviews", ["product_id"], unique=False)
    op.create_table("review_summaries", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("product_review_id", sa.Integer(), sa.ForeignKey("product_reviews.id"), nullable=False), sa.Column("summary", sa.Text(), nullable=False), sa.Column("sentiment", sa.String(length=100)), *_timestamps())
    op.create_index("ix_review_summaries_product_review_id", "review_summaries", ["product_review_id"], unique=False)
    op.create_table("article_briefs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id"), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("brief_markdown", sa.Text()), sa.Column("outline_json", sa.JSON()), *_timestamps())
    op.create_index("ix_article_briefs_article_job_id", "article_briefs", ["article_job_id"], unique=False)
    op.create_table("article_drafts", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id"), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("draft_markdown", sa.Text()), sa.Column("model_name", sa.String(length=255)), *_timestamps())
    op.create_index("ix_article_drafts_article_job_id", "article_drafts", ["article_job_id"], unique=False)
    op.create_table("qa_reports", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id"), nullable=False), sa.Column("status", sa.String(length=100), nullable=False), sa.Column("score", sa.Float()), sa.Column("findings_json", sa.JSON()), sa.Column("summary", sa.Text()), *_timestamps())
    op.create_index("ix_qa_reports_article_job_id", "qa_reports", ["article_job_id"], unique=False)
    op.create_table("wordpress_exports", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id"), nullable=False), sa.Column("export_status", sa.String(length=100), nullable=False), sa.Column("wordpress_post_id", sa.String(length=255)), sa.Column("wordpress_status", sa.String(length=50), nullable=False), sa.Column("response_payload", sa.JSON()), *_timestamps())
    op.create_index("ix_wordpress_exports_article_job_id", "wordpress_exports", ["article_job_id"], unique=False)
    op.create_table("internal_links", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id"), nullable=False), sa.Column("anchor_text", sa.String(length=255), nullable=False), sa.Column("target_url", sa.String(length=1000), nullable=False), sa.Column("notes", sa.Text()), *_timestamps())
    op.create_index("ix_internal_links_article_job_id", "internal_links", ["article_job_id"], unique=False)
    op.create_table("cost_logs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("provider", sa.String(length=100), nullable=False), sa.Column("action", sa.String(length=100), nullable=False), sa.Column("cost_amount", sa.Float()), sa.Column("currency", sa.String(length=16)), sa.Column("related_entity_type", sa.String(length=100)), sa.Column("related_entity_id", sa.Integer()), sa.Column("notes", sa.Text()), *_timestamps())
    op.create_index("ix_cost_logs_provider", "cost_logs", ["provider"], unique=False)
    op.create_table("app_logs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("level", sa.String(length=20), nullable=False), sa.Column("event_type", sa.String(length=100), nullable=False), sa.Column("message", sa.Text(), nullable=False), sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id")), sa.Column("metadata_json", sa.JSON()), *_timestamps())
    op.create_index("ix_app_logs_level", "app_logs", ["level"], unique=False)
    op.create_index("ix_app_logs_event_type", "app_logs", ["event_type"], unique=False)
    op.create_index("ix_app_logs_article_job_id", "app_logs", ["article_job_id"], unique=False)
    op.create_table("app_settings", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("key", sa.String(length=255), nullable=False), sa.Column("value", sa.Text()), sa.Column("description", sa.Text()), *_timestamps())
    op.create_index("ix_app_settings_key", "app_settings", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_app_settings_key", table_name="app_settings")
    op.drop_table("app_settings")
    op.drop_index("ix_app_logs_article_job_id", table_name="app_logs")
    op.drop_index("ix_app_logs_event_type", table_name="app_logs")
    op.drop_index("ix_app_logs_level", table_name="app_logs")
    op.drop_table("app_logs")
    op.drop_index("ix_cost_logs_provider", table_name="cost_logs")
    op.drop_table("cost_logs")
    op.drop_index("ix_internal_links_article_job_id", table_name="internal_links")
    op.drop_table("internal_links")
    op.drop_index("ix_wordpress_exports_article_job_id", table_name="wordpress_exports")
    op.drop_table("wordpress_exports")
    op.drop_index("ix_qa_reports_article_job_id", table_name="qa_reports")
    op.drop_table("qa_reports")
    op.drop_index("ix_article_drafts_article_job_id", table_name="article_drafts")
    op.drop_table("article_drafts")
    op.drop_index("ix_article_briefs_article_job_id", table_name="article_briefs")
    op.drop_table("article_briefs")
    op.drop_index("ix_review_summaries_product_review_id", table_name="review_summaries")
    op.drop_table("review_summaries")
    op.drop_index("ix_product_reviews_product_id", table_name="product_reviews")
    op.drop_table("product_reviews")
    op.drop_index("ix_product_sources_source_id", table_name="product_sources")
    op.drop_index("ix_product_sources_product_id", table_name="product_sources")
    op.drop_table("product_sources")
    op.drop_index("ix_competitor_pages_article_job_id", table_name="competitor_pages")
    op.drop_table("competitor_pages")
    op.drop_index("ix_keyword_research_article_job_id", table_name="keyword_research")
    op.drop_table("keyword_research")
    op.drop_index("ix_serp_results_article_job_id", table_name="serp_results")
    op.drop_table("serp_results")
    op.drop_index("ix_sources_article_job_id", table_name="sources")
    op.drop_table("sources")
    op.drop_index("ix_products_name", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_article_jobs_status", table_name="article_jobs")
    op.drop_index("ix_article_jobs_primary_keyword", table_name="article_jobs")
    op.drop_index("ix_article_jobs_title", table_name="article_jobs")
    op.drop_table("article_jobs")
    op.drop_index("ix_content_clusters_name", table_name="content_clusters")
    op.drop_table("content_clusters")
