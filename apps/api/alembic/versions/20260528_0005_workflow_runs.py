"""workflow runs for research brief and full draft mode

Revision ID: 20260528_0005
Revises: 20260528_0004
Create Date: 2026-05-28 14:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260528_0005"
down_revision = "20260528_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "workflow_runs" not in inspector.get_table_names():
        op.create_table(
            "workflow_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("article_job_id", sa.Integer(), sa.ForeignKey("article_jobs.id"), nullable=False),
            sa.Column("workflow_mode", sa.String(length=50), nullable=False),
            sa.Column("research_mode", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("current_step", sa.String(length=100), nullable=True),
            sa.Column("summary_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    workflow_run_indexes = {idx["name"] for idx in inspector.get_indexes("workflow_runs")} if "workflow_runs" in inspector.get_table_names() else set()
    if "ix_workflow_runs_article_job_id" not in workflow_run_indexes:
        op.create_index("ix_workflow_runs_article_job_id", "workflow_runs", ["article_job_id"], unique=False)
    if "ix_workflow_runs_status" not in workflow_run_indexes:
        op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"], unique=False)

    if "workflow_run_steps" not in inspector.get_table_names():
        op.create_table(
            "workflow_run_steps",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("workflow_run_id", sa.Integer(), sa.ForeignKey("workflow_runs.id"), nullable=False),
            sa.Column("step_key", sa.String(length=100), nullable=False),
            sa.Column("step_label", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    workflow_step_indexes = {idx["name"] for idx in inspector.get_indexes("workflow_run_steps")} if "workflow_run_steps" in inspector.get_table_names() else set()
    if "ix_workflow_run_steps_workflow_run_id" not in workflow_step_indexes:
        op.create_index("ix_workflow_run_steps_workflow_run_id", "workflow_run_steps", ["workflow_run_id"], unique=False)
    if "ix_workflow_run_steps_step_key" not in workflow_step_indexes:
        op.create_index("ix_workflow_run_steps_step_key", "workflow_run_steps", ["step_key"], unique=False)
    if "ix_workflow_run_steps_status" not in workflow_step_indexes:
        op.create_index("ix_workflow_run_steps_status", "workflow_run_steps", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_workflow_run_steps_status", table_name="workflow_run_steps")
    op.drop_index("ix_workflow_run_steps_step_key", table_name="workflow_run_steps")
    op.drop_index("ix_workflow_run_steps_workflow_run_id", table_name="workflow_run_steps")
    op.drop_table("workflow_run_steps")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_article_job_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
