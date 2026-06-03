"""article product url cleanup fields

Revision ID: 20260528_0008
Revises: 20260528_0007_ai_draft_pipeline
Create Date: 2026-05-28 20:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260528_0008"
down_revision = "20260528_0007_ai_draft_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("article_job_products")}

    if "original_source_url" not in columns:
        op.add_column("article_job_products", sa.Column("original_source_url", sa.String(length=1000), nullable=True))
    if "cleaned_source_url" not in columns:
        op.add_column("article_job_products", sa.Column("cleaned_source_url", sa.String(length=1000), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE article_job_products
            SET original_source_url = COALESCE(original_source_url, source_url),
                cleaned_source_url = COALESCE(cleaned_source_url, source_url)
            """
        )
    )


def downgrade() -> None:
    op.drop_column("article_job_products", "cleaned_source_url")
    op.drop_column("article_job_products", "original_source_url")
