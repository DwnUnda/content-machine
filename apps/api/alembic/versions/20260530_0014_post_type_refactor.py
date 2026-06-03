"""Replace article_type with post_type (snake_case values)

Adds a new post_type column, backfills it from the legacy article_type column
using the old-to-new value mapping, then sets it NOT NULL.  The article_type
column is intentionally left in place as a read-only fallback for old JSON
exports; it can be dropped in a future migration once all exports are regenerated.

Revision ID: 20260530_0014
Revises: 20260530_0013
Create Date: 2026-05-30 12:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "20260530_0014"
down_revision = "20260530_0013"
branch_labels = None
depends_on = None

_LEGACY_MAP = {
    "Money page": "money_post",
    "Buying guide": "money_post",
    "Problem-solving post": "informational_blog",
    "Comparison post": "product_comparison",
    "Informational support post": "informational_blog",
    "Product review-style page": "single_product_review",
}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = {c["name"] for c in inspector.get_columns("article_jobs")}

    # Add post_type column (nullable so we can backfill first).
    if "post_type" not in columns:
        op.add_column("article_jobs", sa.Column("post_type", sa.String(100), nullable=True))

    # Backfill: map legacy article_type values → new snake_case post_type values.
    for old_val, new_val in _LEGACY_MAP.items():
        conn.execute(
            text("UPDATE article_jobs SET post_type = :new WHERE article_type = :old"),
            {"new": new_val, "old": old_val},
        )

    # Any rows that already had a snake_case post_type value (e.g. from a partial
    # run) or unknown values: copy article_type verbatim as fallback.
    conn.execute(
        text("UPDATE article_jobs SET post_type = article_type WHERE post_type IS NULL")
    )

    # Make post_type NOT NULL now that every row has a value.
    with op.batch_alter_table("article_jobs") as batch_op:
        batch_op.alter_column("post_type", nullable=False)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = {c["name"] for c in inspector.get_columns("article_jobs")}
    if "post_type" in columns:
        with op.batch_alter_table("article_jobs") as batch_op:
            batch_op.drop_column("post_type")
