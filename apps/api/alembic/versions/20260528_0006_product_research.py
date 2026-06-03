"""product research and article product links

Revision ID: 20260528_0006
Revises: 20260528_0005
Create Date: 2026-05-28 16:15:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260528_0006"
down_revision = "20260528_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    product_columns = {col["name"] for col in inspector.get_columns("products")}
    additions = [
        ("model_number", sa.Column("model_number", sa.String(length=255), nullable=True)),
        ("retailer_domain", sa.Column("retailer_domain", sa.String(length=255), nullable=True)),
        ("price_text", sa.Column("price_text", sa.String(length=255), nullable=True)),
        ("capacity_text", sa.Column("capacity_text", sa.String(length=255), nullable=True)),
        ("tank_size_text", sa.Column("tank_size_text", sa.String(length=255), nullable=True)),
        ("noise_level_text", sa.Column("noise_level_text", sa.String(length=255), nullable=True)),
        ("power_use_text", sa.Column("power_use_text", sa.String(length=255), nullable=True)),
        ("warranty_text", sa.Column("warranty_text", sa.String(length=255), nullable=True)),
        ("drainage_text", sa.Column("drainage_text", sa.String(length=255), nullable=True)),
        ("room_size_text", sa.Column("room_size_text", sa.String(length=255), nullable=True)),
        ("review_rating_text", sa.Column("review_rating_text", sa.String(length=255), nullable=True)),
        ("review_count_text", sa.Column("review_count_text", sa.String(length=255), nullable=True)),
        ("description_snippet", sa.Column("description_snippet", sa.Text(), nullable=True)),
        ("visible_specs_table", sa.Column("visible_specs_table", sa.JSON(), nullable=True)),
        ("confidence_level", sa.Column("confidence_level", sa.String(length=50), nullable=True)),
        ("confidence_score", sa.Column("confidence_score", sa.Integer(), nullable=True)),
        ("common_positives", sa.Column("common_positives", sa.Text(), nullable=True)),
        ("common_complaints", sa.Column("common_complaints", sa.Text(), nullable=True)),
        ("who_should_buy", sa.Column("who_should_buy", sa.Text(), nullable=True)),
        ("who_should_avoid", sa.Column("who_should_avoid", sa.Text(), nullable=True)),
        ("best_for", sa.Column("best_for", sa.Text(), nullable=True)),
        ("bottom_line", sa.Column("bottom_line", sa.Text(), nullable=True)),
        ("extraction_status", sa.Column("extraction_status", sa.String(length=50), nullable=True)),
        ("extraction_error", sa.Column("extraction_error", sa.Text(), nullable=True)),
        ("raw_extracted_json", sa.Column("raw_extracted_json", sa.JSON(), nullable=True)),
    ]
    for name, column in additions:
        if name not in product_columns:
            op.add_column("products", column)

    if "article_job_products" not in inspector.get_table_names():
        op.create_table(
            "article_job_products",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
            sa.Column("source_url", sa.String(length=1000), nullable=False),
            sa.Column("source_type", sa.String(length=100), nullable=False),
            sa.Column("extraction_status", sa.String(length=50), nullable=True),
            sa.Column("extraction_error", sa.Text(), nullable=True),
            sa.Column("raw_extracted_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    indexes = {idx["name"] for idx in inspector.get_indexes("article_job_products")} if "article_job_products" in inspector.get_table_names() else set()
    if "ix_article_job_products_article_job_id" not in indexes:
        op.create_index("ix_article_job_products_article_job_id", "article_job_products", ["article_job_id"], unique=False)
    if "ix_article_job_products_product_id" not in indexes:
        op.create_index("ix_article_job_products_product_id", "article_job_products", ["product_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_article_job_products_product_id", table_name="article_job_products")
    op.drop_index("ix_article_job_products_article_job_id", table_name="article_job_products")
    op.drop_table("article_job_products")
    op.drop_column("products", "raw_extracted_json")
    op.drop_column("products", "extraction_error")
    op.drop_column("products", "extraction_status")
    op.drop_column("products", "bottom_line")
    op.drop_column("products", "best_for")
    op.drop_column("products", "who_should_avoid")
    op.drop_column("products", "who_should_buy")
    op.drop_column("products", "common_complaints")
    op.drop_column("products", "common_positives")
    op.drop_column("products", "confidence_score")
    op.drop_column("products", "confidence_level")
    op.drop_column("products", "visible_specs_table")
    op.drop_column("products", "description_snippet")
    op.drop_column("products", "review_count_text")
    op.drop_column("products", "review_rating_text")
    op.drop_column("products", "room_size_text")
    op.drop_column("products", "drainage_text")
    op.drop_column("products", "warranty_text")
    op.drop_column("products", "power_use_text")
    op.drop_column("products", "noise_level_text")
    op.drop_column("products", "tank_size_text")
    op.drop_column("products", "capacity_text")
    op.drop_column("products", "price_text")
    op.drop_column("products", "retailer_domain")
    op.drop_column("products", "model_number")
