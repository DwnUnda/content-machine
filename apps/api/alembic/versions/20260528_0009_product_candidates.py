"""product candidates

Revision ID: 20260528_0009
Revises: 20260528_0008
Create Date: 2026-05-28 21:05:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260528_0009"
down_revision = "20260528_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "product_candidates" not in inspector.get_table_names():
        op.create_table(
            "product_candidates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id"), nullable=False),
            sa.Column("product_name", sa.String(length=255), nullable=False),
            sa.Column("brand", sa.String(length=255), nullable=True),
            sa.Column("model_number", sa.String(length=255), nullable=True),
            sa.Column("source_url", sa.String(length=1000), nullable=True),
            sa.Column("source_domain", sa.String(length=255), nullable=True),
            sa.Column("source_type", sa.String(length=100), nullable=False),
            sa.Column("reason_found", sa.Text(), nullable=True),
            sa.Column("found_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("confidence_score", sa.Integer(), nullable=True),
            sa.Column("suggested_best_for", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="suggested"),
            sa.Column("raw_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("product_candidates")} if "product_candidates" in inspector.get_table_names() else set()
    if "ix_product_candidates_article_job_id" not in indexes:
        op.create_index("ix_product_candidates_article_job_id", "product_candidates", ["article_job_id"], unique=False)
    if "ix_product_candidates_product_name" not in indexes:
        op.create_index("ix_product_candidates_product_name", "product_candidates", ["product_name"], unique=False)
    if "ix_product_candidates_status" not in indexes:
        op.create_index("ix_product_candidates_status", "product_candidates", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_product_candidates_status", table_name="product_candidates")
    op.drop_index("ix_product_candidates_product_name", table_name="product_candidates")
    op.drop_index("ix_product_candidates_article_job_id", table_name="product_candidates")
    op.drop_table("product_candidates")
