"""competitor extraction and serp analysis

Revision ID: 20260528_0004
Revises: 20260527_0003
Create Date: 2026-05-28 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260528_0004"
down_revision = "20260527_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    competitor_columns = {col["name"] for col in inspector.get_columns("competitor_pages")}

    competitor_additions = [
        ("serp_result_id", sa.Column("serp_result_id", sa.Integer(), nullable=True)),
        ("domain", sa.Column("domain", sa.String(length=255), nullable=True)),
        ("meta_description", sa.Column("meta_description", sa.Text(), nullable=True)),
        ("h1", sa.Column("h1", sa.Text(), nullable=True)),
        ("h2_list", sa.Column("h2_list", sa.JSON(), nullable=True)),
        ("h3_list", sa.Column("h3_list", sa.JSON(), nullable=True)),
        ("word_count_estimate", sa.Column("word_count_estimate", sa.Integer(), nullable=True)),
        ("visible_text_extract", sa.Column("visible_text_extract", sa.Text(), nullable=True)),
        ("detected_product_names", sa.Column("detected_product_names", sa.JSON(), nullable=True)),
        ("tables_count", sa.Column("tables_count", sa.Integer(), nullable=True)),
        ("faq_headings", sa.Column("faq_headings", sa.JSON(), nullable=True)),
        ("affiliate_indicators", sa.Column("affiliate_indicators", sa.JSON(), nullable=True)),
        ("australian_relevance_signals", sa.Column("australian_relevance_signals", sa.JSON(), nullable=True)),
        ("australian_relevance_score", sa.Column("australian_relevance_score", sa.Integer(), nullable=True)),
        ("extraction_method", sa.Column("extraction_method", sa.String(length=50), nullable=True)),
        ("extraction_status", sa.Column("extraction_status", sa.String(length=50), nullable=True)),
        ("error_message", sa.Column("error_message", sa.Text(), nullable=True)),
        ("raw_extracted_data_json", sa.Column("raw_extracted_data_json", sa.JSON(), nullable=True)),
    ]
    for name, column in competitor_additions:
        if name not in competitor_columns:
            op.add_column("competitor_pages", column)

    competitor_indexes = {idx["name"] for idx in inspector.get_indexes("competitor_pages")}
    if "ix_competitor_pages_serp_result_id" not in competitor_indexes:
        op.create_index("ix_competitor_pages_serp_result_id", "competitor_pages", ["serp_result_id"], unique=False)

    if "competitor_analysis_reports" not in inspector.get_table_names():
        op.create_table(
            "competitor_analysis_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id"), nullable=False),
            sa.Column("dominant_intent", sa.String(length=100)),
            sa.Column("dominant_page_types_json", sa.JSON()),
            sa.Column("common_headings_json", sa.JSON()),
            sa.Column("common_questions_json", sa.JSON()),
            sa.Column("repeated_products_json", sa.JSON()),
            sa.Column("competitor_gaps_json", sa.JSON()),
            sa.Column("australian_context_gaps_json", sa.JSON()),
            sa.Column("recommended_angle", sa.Text()),
            sa.Column("original_value_recommendations_json", sa.JSON()),
            sa.Column("suggested_support_articles_json", sa.JSON()),
            sa.Column("difficulty_estimate", sa.String(length=50)),
            sa.Column("raw_report_json", sa.JSON()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    analysis_indexes = {idx["name"] for idx in inspector.get_indexes("competitor_analysis_reports")} if "competitor_analysis_reports" in inspector.get_table_names() else set()
    if "ix_competitor_analysis_reports_article_job_id" not in analysis_indexes:
        op.create_index("ix_competitor_analysis_reports_article_job_id", "competitor_analysis_reports", ["article_job_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_competitor_analysis_reports_article_job_id", table_name="competitor_analysis_reports")
    op.drop_table("competitor_analysis_reports")
    op.drop_index("ix_competitor_pages_serp_result_id", table_name="competitor_pages")
    op.drop_column("competitor_pages", "raw_extracted_data_json")
    op.drop_column("competitor_pages", "error_message")
    op.drop_column("competitor_pages", "extraction_status")
    op.drop_column("competitor_pages", "extraction_method")
    op.drop_column("competitor_pages", "australian_relevance_score")
    op.drop_column("competitor_pages", "australian_relevance_signals")
    op.drop_column("competitor_pages", "affiliate_indicators")
    op.drop_column("competitor_pages", "faq_headings")
    op.drop_column("competitor_pages", "tables_count")
    op.drop_column("competitor_pages", "detected_product_names")
    op.drop_column("competitor_pages", "visible_text_extract")
    op.drop_column("competitor_pages", "word_count_estimate")
    op.drop_column("competitor_pages", "h3_list")
    op.drop_column("competitor_pages", "h2_list")
    op.drop_column("competitor_pages", "h1")
    op.drop_column("competitor_pages", "meta_description")
    op.drop_column("competitor_pages", "domain")
    op.drop_column("competitor_pages", "serp_result_id")
