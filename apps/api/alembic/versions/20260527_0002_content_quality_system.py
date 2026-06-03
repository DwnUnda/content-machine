"""content quality system

Revision ID: 20260527_0002
Revises: 20260527_0001
Create Date: 2026-05-27 16:50:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260527_0002"
down_revision = "20260527_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("article_jobs", sa.Column("review_override", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("article_jobs", sa.Column("current_qa_score", sa.Float(), nullable=True))
    op.add_column("qa_reports", sa.Column("passed_gate", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("app_settings", sa.Column("category", sa.String(length=100), nullable=True))
    op.create_index("ix_app_settings_category", "app_settings", ["category"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_app_settings_category", table_name="app_settings")
    op.drop_column("app_settings", "category")
    op.drop_column("qa_reports", "passed_gate")
    op.drop_column("article_jobs", "current_qa_score")
    op.drop_column("article_jobs", "review_override")
