"""dataforseo fields

Revision ID: 20260527_0003
Revises: 20260527_0002
Create Date: 2026-05-27 18:05:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260527_0003"
down_revision = "20260527_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("serp_results", sa.Column("domain", sa.String(length=255), nullable=True))
    op.add_column("serp_results", sa.Column("result_type", sa.String(length=100), nullable=True))
    op.add_column("keyword_research", sa.Column("cpc", sa.Float(), nullable=True))
    op.add_column("keyword_research", sa.Column("competition", sa.String(length=100), nullable=True))
    op.add_column("keyword_research", sa.Column("source", sa.String(length=100), nullable=True))
    op.add_column("keyword_research", sa.Column("source_payload", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("keyword_research", "source_payload")
    op.drop_column("keyword_research", "source")
    op.drop_column("keyword_research", "competition")
    op.drop_column("keyword_research", "cpc")
    op.drop_column("serp_results", "result_type")
    op.drop_column("serp_results", "domain")
