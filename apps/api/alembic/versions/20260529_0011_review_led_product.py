"""review-led product analysis layer fields on products

Revision ID: 20260529_0011
Revises: 20260529_0010
Create Date: 2026-05-29 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260529_0011"
down_revision = "20260529_0010"
branch_labels = None
depends_on = None


NEW_COLUMNS = (
    ("manufacturer_url", sa.String(length=1000)),
    ("retailer_urls", sa.JSON()),
    ("positive_review_patterns", sa.Text()),
    ("negative_review_patterns", sa.Text()),
    ("reliability_concerns", sa.Text()),
    ("key_specs", sa.JSON()),
    ("price_range_text", sa.String(length=255)),
    ("australian_availability", sa.String(length=255)),
    ("review_methodology_notes", sa.Text()),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = {col["name"] for col in inspector.get_columns("products")}
    for name, col_type in NEW_COLUMNS:
        if name not in columns:
            op.add_column("products", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = {col["name"] for col in inspector.get_columns("products")}
    for name, _ in reversed(NEW_COLUMNS):
        if name in columns:
            op.drop_column("products", name)
