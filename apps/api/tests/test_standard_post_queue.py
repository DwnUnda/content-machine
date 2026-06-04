from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import ArticleJob, ArticleJobStatus, StandardPostBatch, StandardPostBatchItem, WorkflowRun


def test_batch_detail_recovers_completed_stale_running_item():
    client = TestClient(app)

    old_time = datetime.utcnow() - timedelta(minutes=30)
    with SessionLocal() as db:
        job = ArticleJob(
            title="What Humidity Level Causes Mould In Australian Homes?",
            primary_keyword="What Humidity Level Causes Mould In Australian Homes?",
            post_type="informational_blog",
            status=ArticleJobStatus.READY_FOR_REVIEW.value,
            current_qa_score=88,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        db.add(
            WorkflowRun(
                article_job_id=job.id,
                workflow_mode="full_draft",
                research_mode="fresh",
                status="complete",
                current_step=None,
                summary_message="Full draft workflow completed.",
                created_at=old_time,
                updated_at=old_time,
            )
        )
        batch = StandardPostBatch(status="running", summary_message="Queue started.", wordpress_mode="local_only")
        batch.items.append(
            StandardPostBatchItem(
                keyword=job.title,
                slug="what-humidity-level-causes-mould-in-australian-homes",
                position=0,
                status="running",
                current_step="running_workflow",
                article_job_id=job.id,
                started_at=old_time,
            )
        )
        batch.items.append(
            StandardPostBatchItem(
                keyword="Will A Dehumidifier Remove Existing Mould?",
                slug="will-a-dehumidifier-remove-existing-mould",
                position=1,
                status="pending",
            )
        )
        db.add(batch)
        db.commit()
        batch_id = batch.id

    response = client.get(f"/api/standard-post-batches/{batch_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["summary_message"] == "Queue recovered after interruption. Click Start to continue pending items."
    assert payload["counts"]["complete"] == 1
    assert payload["counts"]["pending"] == 1
    first = payload["items"][0]
    assert first["status"] == "complete"
    assert first["current_step"] is None
    assert first["article_folder"]


def test_batch_detail_leaves_recent_running_workflow_item_running():
    client = TestClient(app)

    recent_time = datetime.utcnow() - timedelta(minutes=2)
    with SessionLocal() as db:
        job = ArticleJob(
            title="Will A Dehumidifier Remove Existing Mould?",
            primary_keyword="Will A Dehumidifier Remove Existing Mould?",
            post_type="informational_blog",
            status=ArticleJobStatus.BRIEF_READY.value,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        db.add(
            WorkflowRun(
                article_job_id=job.id,
                workflow_mode="full_draft",
                research_mode="fresh",
                status="running",
                current_step="reddit_feedback",
                created_at=recent_time,
                updated_at=recent_time,
            )
        )
        batch = StandardPostBatch(status="running", summary_message="Queue started.", wordpress_mode="local_only")
        batch.items.append(
            StandardPostBatchItem(
                keyword=job.title,
                slug="will-a-dehumidifier-remove-existing-mould",
                position=0,
                status="running",
                current_step="running_workflow",
                article_job_id=job.id,
                started_at=recent_time,
            )
        )
        db.add(batch)
        db.commit()
        batch_id = batch.id

    response = client.get(f"/api/standard-post-batches/{batch_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["counts"]["running"] == 1
    first = payload["items"][0]
    assert first["status"] == "running"
    assert first["current_step"] == "running_workflow"
