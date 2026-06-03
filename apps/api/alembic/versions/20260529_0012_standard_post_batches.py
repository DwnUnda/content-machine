"""standard post batches for bulk keyword queue

Revision ID: 20260529_0012
Revises: 20260529_0011
Create Date: 2026-05-29 16:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260529_0012"
down_revision = "20260529_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "standard_post_batches" not in inspector.get_table_names():
        op.create_table(
            "standard_post_batches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
            sa.Column("wordpress_mode", sa.String(length=50), nullable=False, server_default="local_only"),
            sa.Column("summary_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    batch_indexes = (
        {idx["name"] for idx in inspector.get_indexes("standard_post_batches")}
        if "standard_post_batches" in inspector.get_table_names()
        else set()
    )
    if "ix_standard_post_batches_status" not in batch_indexes:
        op.create_index("ix_standard_post_batches_status", "standard_post_batches", ["status"], unique=False)

    if "standard_post_batch_items" not in inspector.get_table_names():
        op.create_table(
            "standard_post_batch_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("batch_id", sa.Integer(), sa.ForeignKey("standard_post_batches.id"), nullable=False),
            sa.Column("keyword", sa.String(length=500), nullable=False),
            sa.Column("slug", sa.String(length=255), nullable=True),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
            sa.Column("current_step", sa.String(length=100), nullable=True),
            sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id"), nullable=True),
            sa.Column("article_folder", sa.String(length=1000), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    item_indexes = (
        {idx["name"] for idx in inspector.get_indexes("standard_post_batch_items")}
        if "standard_post_batch_items" in inspector.get_table_names()
        else set()
    )
    if "ix_standard_post_batch_items_batch_id" not in item_indexes:
        op.create_index(
            "ix_standard_post_batch_items_batch_id", "standard_post_batch_items", ["batch_id"], unique=False
        )
    if "ix_standard_post_batch_items_slug" not in item_indexes:
        op.create_index(
            "ix_standard_post_batch_items_slug", "standard_post_batch_items", ["slug"], unique=False
        )
    if "ix_standard_post_batch_items_status" not in item_indexes:
        op.create_index(
            "ix_standard_post_batch_items_status", "standard_post_batch_items", ["status"], unique=False
        )
    if "ix_standard_post_batch_items_article_job_id" not in item_indexes:
        op.create_index(
            "ix_standard_post_batch_items_article_job_id",
            "standard_post_batch_items",
            ["article_job_id"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_standard_post_batch_items_article_job_id", table_name="standard_post_batch_items")
    op.drop_index("ix_standard_post_batch_items_status", table_name="standard_post_batch_items")
    op.drop_index("ix_standard_post_batch_items_slug", table_name="standard_post_batch_items")
    op.drop_index("ix_standard_post_batch_items_batch_id", table_name="standard_post_batch_items")
    op.drop_table("standard_post_batch_items")
    op.drop_index("ix_standard_post_batches_status", table_name="standard_post_batches")
    op.drop_table("standard_post_batches")
