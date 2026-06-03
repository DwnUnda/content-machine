"""ai draft pipeline

Revision ID: 20260528_0007_ai_draft_pipeline
Revises: 20260528_0006
Create Date: 2026-05-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260528_0007_ai_draft_pipeline"
down_revision = "20260528_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    article_draft_columns = {col["name"] for col in inspector.get_columns("article_drafts")}
    with op.batch_alter_table("article_drafts") as batch_op:
        if "stage" not in article_draft_columns:
            batch_op.add_column(sa.Column("stage", sa.String(length=50), nullable=True))
        if "seo_title" not in article_draft_columns:
            batch_op.add_column(sa.Column("seo_title", sa.String(length=255), nullable=True))
        if "meta_description" not in article_draft_columns:
            batch_op.add_column(sa.Column("meta_description", sa.String(length=500), nullable=True))
        if "slug" not in article_draft_columns:
            batch_op.add_column(sa.Column("slug", sa.String(length=255), nullable=True))
        if "excerpt" not in article_draft_columns:
            batch_op.add_column(sa.Column("excerpt", sa.Text(), nullable=True))
        if "prompt_name" not in article_draft_columns:
            batch_op.add_column(sa.Column("prompt_name", sa.String(length=255), nullable=True))
        if "source_payload_json" not in article_draft_columns:
            batch_op.add_column(sa.Column("source_payload_json", sa.JSON(), nullable=True))

    qa_report_columns = {col["name"] for col in inspector.get_columns("qa_reports")}
    with op.batch_alter_table("qa_reports") as batch_op:
        if "model_name" not in qa_report_columns:
            batch_op.add_column(sa.Column("model_name", sa.String(length=255), nullable=True))
        if "prompt_name" not in qa_report_columns:
            batch_op.add_column(sa.Column("prompt_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("qa_reports") as batch_op:
        batch_op.drop_column("prompt_name")
        batch_op.drop_column("model_name")

    with op.batch_alter_table("article_drafts") as batch_op:
        batch_op.drop_column("source_payload_json")
        batch_op.drop_column("prompt_name")
        batch_op.drop_column("excerpt")
        batch_op.drop_column("slug")
        batch_op.drop_column("meta_description")
        batch_op.drop_column("seo_title")
        batch_op.drop_column("stage")
