"""serp intent classifier output on article briefs

Revision ID: 20260529_0010
Revises: 20260528_0009
Create Date: 2026-05-29 09:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260529_0010"
down_revision = "20260528_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = {col["name"] for col in inspector.get_columns("article_briefs")}
    if "serp_intent_json" not in columns:
        op.add_column("article_briefs", sa.Column("serp_intent_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = {col["name"] for col in inspector.get_columns("article_briefs")}
    if "serp_intent_json" in columns:
        op.drop_column("article_briefs", "serp_intent_json")
