"""product recommendation role label

Revision ID: 20260530_0013
Revises: 20260529_0012
Create Date: 2026-05-30 09:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260530_0013"
down_revision = "20260529_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("products")}
    if "role" not in columns:
        op.add_column("products", sa.Column("role", sa.String(length=100), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("products")}
    if "role" in columns:
        op.drop_column("products", "role")
