"""Make article_type nullable so ORM inserts (post_type only) succeed

The previous migration (0014) added post_type and left article_type in place
as a read-only fallback, but kept its NOT NULL constraint. The ORM model no
longer writes article_type, so every INSERT fails with IntegrityError. This
migration relaxes the constraint to nullable.

Revision ID: 20260531_0015
Revises: 20260530_0014
Create Date: 2026-05-31 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260531_0015"
down_revision = "20260530_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("article_jobs") as batch_op:
        batch_op.alter_column("article_type", existing_type=sa.String(100), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("article_jobs") as batch_op:
        batch_op.alter_column("article_type", existing_type=sa.String(100), nullable=False)
