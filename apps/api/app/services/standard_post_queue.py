"""Bulk Standard Posts queue worker.

Processes a batch of standard (informational) article posts one keyword at a time,
reusing the existing single-article workflow (`workflow.run_full_workflow`). It runs
in a background thread so the HTTP request that starts it returns immediately.

Key behaviours (per spec):
- Standard informational posts only. Forces ArticleType.INFORMATIONAL, which is NOT
  product-gated, so no product cards / product URLs are required and the money-page
  workflow is never triggered.
- One keyword at a time. No parallel processing.
- On failure: mark the item failed, save the error, and continue with the next item.
- Pause / resume / cancel are honoured between items (checked before each item and
  before starting work on an item).
- Progress is persisted after every item (DB commit) for crash recovery.
- A JSON mirror is written to Completed-Articles/batches/ for crash recovery.
- WordPress: default `local_only`. If `local_plus_draft`, export a DRAFT only after a
  successful article (never publishes). A WordPress failure does not fail the article.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import COMPLETED_ARTICLES_DIR
from app.db.session import SessionLocal
from app.models.entities import (
    ArticleJob,
    ArticleJobStatus,
    PostType,
    StandardPostBatch,
    StandardPostBatchItem,
    WorkflowRun,
)
from app.repositories.crud import CRUDRepository
from app.services.keyword_parser import slugify
from app.services.local_exports import sync_article_export
from app.services.logging import create_app_log
from app.services import workflow as workflow_service


STANDARD_POST_ARTICLE_TYPE = PostType.INFORMATIONAL_BLOG.value
RUNNING_WORKFLOW_STALE_AFTER = timedelta(minutes=20)

# Active worker threads keyed by batch id, guarding against double-start.
_active_workers: dict[int, threading.Thread] = {}
_lock = threading.Lock()

_job_repo = CRUDRepository(ArticleJob)


def _batches_dir() -> Path:
    path = COMPLETED_ARTICLES_DIR / "batches"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _mirror_batch_to_json(batch: StandardPostBatch) -> None:
    """Write a crash-recovery JSON mirror of the batch and its items."""
    try:
        payload = {
            "batch_id": batch.id,
            "name": batch.name,
            "type": "standard_post",
            "status": batch.status,
            "wordpress_mode": batch.wordpress_mode,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
            "items": [
                {
                    "id": item.id,
                    "keyword": item.keyword,
                    "slug": item.slug,
                    "position": item.position,
                    "status": item.status,
                    "current_step": item.current_step,
                    "article_job_id": item.article_job_id,
                    "article_folder": item.article_folder,
                    "error": item.error_message,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "started_at": item.started_at.isoformat() if item.started_at else None,
                    "completed_at": item.completed_at.isoformat() if item.completed_at else None,
                }
                for item in sorted(batch.items, key=lambda i: i.position)
            ],
        }
        filename = f"batch-standard-posts-{batch.id}.json"
        (_batches_dir() / filename).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        # Mirroring is best-effort; never let it break processing.
        pass


def _slug_exists_in_articles(db: Session, slug: str) -> bool:
    """True if an existing article job already maps to this slug."""
    if not slug:
        return False
    jobs = db.scalars(select(ArticleJob)).all()
    for job in jobs:
        existing = slugify(job.title)
        if existing and existing == slug:
            return True
    return False


def start_batch(db: Session, batch: StandardPostBatch) -> bool:
    """Mark a batch running and launch the background worker.

    Returns False if a worker is already active for this batch.
    """
    with _lock:
        if batch.id in _active_workers and _active_workers[batch.id].is_alive():
            return False

        batch.status = "running"
        batch.summary_message = "Queue started."
        db.add(batch)
        db.commit()
        _mirror_batch_to_json(batch)

        thread = threading.Thread(
            target=_run_batch_worker,
            args=(batch.id,),
            name=f"standard-post-batch-{batch.id}",
            daemon=True,
        )
        _active_workers[batch.id] = thread
        thread.start()
        return True


def maybe_resume_recovered_batch(db: Session, batch: StandardPostBatch) -> bool:
    """Restart a previously-running queue after stale-state recovery."""
    if batch.status != "pending":
        return False
    pending_count = db.scalar(
        select(func.count(StandardPostBatchItem.id)).where(
            StandardPostBatchItem.batch_id == batch.id,
            StandardPostBatchItem.status == "pending",
        )
    )
    if not pending_count:
        return False
    return start_batch(db, batch)


def _run_batch_worker(batch_id: int) -> None:
    """Background worker. Owns its own DB session (SQLite check_same_thread=False)."""
    db = SessionLocal()
    try:
        while True:
            batch = db.get(StandardPostBatch, batch_id)
            if not batch:
                return

            # Honour pause / cancel requested between items.
            if batch.status == "paused":
                batch.summary_message = "Queue paused."
                db.add(batch)
                db.commit()
                _mirror_batch_to_json(batch)
                return
            if batch.status == "cancelled":
                _cancel_remaining(db, batch)
                return

            reconcile_stale_running_items(db, batch)

            item = db.scalar(
                select(StandardPostBatchItem)
                .where(
                    StandardPostBatchItem.batch_id == batch_id,
                    StandardPostBatchItem.status == "pending",
                )
                .order_by(StandardPostBatchItem.position.asc())
            )
            if item is None:
                _finalise_batch(db, batch)
                return

            _process_item(db, batch, item)
    finally:
        db.close()
        with _lock:
            _active_workers.pop(batch_id, None)


def _process_item(db: Session, batch: StandardPostBatch, item: StandardPostBatchItem) -> None:
    item.status = "running"
    item.current_step = "starting"
    item.started_at = datetime.utcnow()
    item.error_message = None
    db.add(item)
    db.commit()
    _mirror_batch_to_json(batch)

    slug = item.slug or slugify(item.keyword)

    # Duplicate protection: skip if an article with the same slug already exists, or
    # the keyword was already completed earlier in this batch.
    already_completed = db.scalar(
        select(func.count(StandardPostBatchItem.id)).where(
            StandardPostBatchItem.batch_id == batch.id,
            StandardPostBatchItem.id != item.id,
            StandardPostBatchItem.status == "complete",
            func.lower(StandardPostBatchItem.keyword) == item.keyword.casefold(),
        )
    )
    if already_completed or _slug_exists_in_articles(db, slug):
        item.status = "skipped"
        item.current_step = None
        item.completed_at = datetime.utcnow()
        item.error_message = "Skipped: an article with this keyword/slug already exists."
        db.add(item)
        db.commit()
        _mirror_batch_to_json(batch)
        return

    try:
        # Reuse the EXACT same path a single standard post uses.
        job = _job_repo.create(
            db,
            {
                "title": item.keyword,
                "primary_keyword": item.keyword,
                "post_type": STANDARD_POST_ARTICLE_TYPE,
                "status": "New",
            },
        )
        item.article_job_id = job.id
        db.add(item)
        db.commit()

        create_app_log(
            db,
            event_type="standard_post_batch.item_created",
            message=f"Bulk standard post job '{job.title}' created from batch {batch.id}.",
            article_job_id=job.id,
        )
        sync_article_export(db, job, reason="article_created")

        item.current_step = "running_workflow"
        db.add(item)
        db.commit()

        run = workflow_service.run_full_workflow(db, job, research_mode="fresh")

        run_status = getattr(run, "status", None)
        if run_status == "failed":
            item.status = "failed"
            item.error_message = getattr(run, "summary_message", None) or "Workflow failed."
        else:
            item.status = "complete"
            item.article_folder = job.local_export_path

            # WordPress draft export is optional and draft-only. Never publishes.
            if batch.wordpress_mode == "local_plus_draft":
                try:
                    workflow_service.export_to_wordpress_draft(db, job)
                except Exception as wp_exc:  # noqa: BLE001 - WP failure must not fail article
                    create_app_log(
                        db,
                        event_type="standard_post_batch.wordpress_failed",
                        message=f"WordPress draft export failed for job {job.id}: {wp_exc}",
                        level="WARNING",
                        article_job_id=job.id,
                    )
        item.current_step = None
    except Exception as exc:  # noqa: BLE001 - one failure must not stop the batch
        item.status = "failed"
        item.current_step = None
        item.error_message = str(exc) or exc.__class__.__name__
        create_app_log(
            db,
            event_type="standard_post_batch.item_failed",
            message=f"Bulk standard post item {item.id} failed: {item.error_message}",
            level="ERROR",
            article_job_id=item.article_job_id,
        )
    finally:
        item.completed_at = datetime.utcnow()
        db.add(item)
        db.commit()
        db.refresh(batch)
        _mirror_batch_to_json(batch)


def reconcile_stale_running_items(db: Session, batch: StandardPostBatch) -> bool:
    """Recover batch rows left running after a worker interruption.

    The article workflow can finish successfully while the batch item still says
    "running" if the process is restarted, the worker thread exits unexpectedly,
    or a manual article action completes the underlying job. This function maps
    those stale rows back to the real article/job state.
    """
    has_active_worker = bool(batch.id in _active_workers and _active_workers[batch.id].is_alive())
    running_items = db.scalars(
        select(StandardPostBatchItem).where(
            StandardPostBatchItem.batch_id == batch.id,
            StandardPostBatchItem.status == "running",
        )
    ).all()
    if not running_items:
        if batch.status == "running" and not has_active_worker:
            pending_count = db.scalar(
                select(func.count(StandardPostBatchItem.id)).where(
                    StandardPostBatchItem.batch_id == batch.id,
                    StandardPostBatchItem.status == "pending",
                )
            )
            if pending_count:
                batch.status = "pending"
                batch.summary_message = "Queue recovered after interruption. Continuing pending items."
                db.add(batch)
                db.commit()
                db.refresh(batch)
                _mirror_batch_to_json(batch)
                return True
            _finalise_batch(db, batch)
            return True
        return False

    changed = False
    now = datetime.utcnow()
    for item in running_items:
        item_changed = False
        job = db.get(ArticleJob, item.article_job_id) if item.article_job_id else None
        latest_run = None
        if job:
            latest_run = db.scalar(
                select(WorkflowRun)
                .where(WorkflowRun.article_job_id == job.id, WorkflowRun.workflow_mode == "full_draft")
                .order_by(desc(WorkflowRun.updated_at), desc(WorkflowRun.created_at), desc(WorkflowRun.id))
            )

        job_complete = bool(
            job
            and (
                job.status in {
                    ArticleJobStatus.READY_FOR_REVIEW.value,
                    ArticleJobStatus.EXPORTED_TO_WORDPRESS.value,
                }
                or (latest_run and latest_run.status == "complete")
            )
        )
        job_failed = bool(latest_run and latest_run.status == "failed")
        workflow_recently_running = bool(
            latest_run
            and latest_run.status == "running"
            and (datetime.utcnow() - (latest_run.updated_at or latest_run.created_at)) < RUNNING_WORKFLOW_STALE_AFTER
        )

        if job_complete:
            item.status = "complete"
            item.current_step = None
            item.article_folder = job.local_export_path if job else item.article_folder
            item.error_message = None
            item.completed_at = item.completed_at or now
            item_changed = True
        elif job_failed:
            item.status = "failed"
            item.current_step = None
            item.error_message = latest_run.summary_message or "Workflow failed."
            item.completed_at = item.completed_at or now
            item_changed = True
        elif workflow_recently_running:
            # Another process/thread may still be working. Do not mark the row
            # failed just because this process does not have that worker in memory.
            continue
        elif not has_active_worker:
            item.status = "failed"
            item.current_step = None
            item.error_message = "Interrupted while running. Retry this item to run it again."
            item.completed_at = item.completed_at or now
            item_changed = True

        if item_changed:
            db.add(item)
            changed = True

    if not changed:
        return False

    db.flush()
    pending_count = db.scalar(
        select(func.count(StandardPostBatchItem.id)).where(
            StandardPostBatchItem.batch_id == batch.id,
            StandardPostBatchItem.status == "pending",
        )
    )
    running_count = db.scalar(
        select(func.count(StandardPostBatchItem.id)).where(
            StandardPostBatchItem.batch_id == batch.id,
            StandardPostBatchItem.status == "running",
        )
    )
    if not running_count and pending_count and not has_active_worker:
        batch.status = "pending"
        batch.summary_message = "Queue recovered after interruption. Continuing pending items."
        db.add(batch)
    db.commit()
    db.refresh(batch)
    _mirror_batch_to_json(batch)
    if not running_count and not pending_count:
        _finalise_batch(db, batch)
    return True


def _cancel_remaining(db: Session, batch: StandardPostBatch) -> None:
    pending = db.scalars(
        select(StandardPostBatchItem).where(
            StandardPostBatchItem.batch_id == batch.id,
            StandardPostBatchItem.status == "pending",
        )
    ).all()
    for item in pending:
        item.status = "cancelled"
        item.current_step = None
        db.add(item)
    batch.status = "cancelled"
    batch.summary_message = "Queue cancelled. Completed items were kept."
    db.add(batch)
    db.commit()
    db.refresh(batch)
    _mirror_batch_to_json(batch)


def _finalise_batch(db: Session, batch: StandardPostBatch) -> None:
    counts = _status_counts(db, batch.id)
    batch.status = "complete"
    batch.summary_message = (
        f"Queue complete. {counts.get('complete', 0)} complete, "
        f"{counts.get('failed', 0)} failed, {counts.get('skipped', 0)} skipped."
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    _mirror_batch_to_json(batch)


def _status_counts(db: Session, batch_id: int) -> dict[str, int]:
    rows = db.execute(
        select(StandardPostBatchItem.status, func.count(StandardPostBatchItem.id))
        .where(StandardPostBatchItem.batch_id == batch_id)
        .group_by(StandardPostBatchItem.status)
    ).all()
    return {status: count for status, count in rows}


def request_pause(db: Session, batch: StandardPostBatch) -> None:
    """Ask the worker to pause after the current item finishes."""
    if batch.status == "running":
        batch.status = "paused"
        batch.summary_message = "Pause requested. Will stop after the current item."
        db.add(batch)
        db.commit()


def resume_batch(db: Session, batch: StandardPostBatch) -> bool:
    """Resume a paused batch by relaunching the worker."""
    if batch.status not in {"paused", "running"}:
        return False
    return start_batch(db, batch)


def request_cancel(db: Session, batch: StandardPostBatch) -> None:
    """Cancel remaining pending items. Completed items are kept."""
    is_running = batch.id in _active_workers and _active_workers[batch.id].is_alive()
    if is_running:
        # Let the running worker observe the cancel between items.
        batch.status = "cancelled"
        batch.summary_message = "Cancel requested. Finishing the current item, then stopping."
        db.add(batch)
        db.commit()
    else:
        _cancel_remaining(db, batch)


def retry_item(db: Session, batch: StandardPostBatch, item: StandardPostBatchItem) -> bool:
    """Reset a failed/skipped/cancelled item to pending so it runs again."""
    if item.status not in {"failed", "skipped", "cancelled"}:
        return False
    item.status = "pending"
    item.current_step = None
    item.error_message = None
    item.article_job_id = None
    item.article_folder = None
    item.started_at = None
    item.completed_at = None
    db.add(item)
    # Move the batch back into a runnable state if it had finished.
    if batch.status in {"complete", "cancelled"}:
        batch.status = "pending"
        batch.summary_message = "Re-queued for retry. Start the queue to process again."
        db.add(batch)
    db.commit()
    db.refresh(batch)
    _mirror_batch_to_json(batch)
    return True


def skip_item(db: Session, item: StandardPostBatchItem) -> bool:
    """Manually skip a pending item."""
    if item.status != "pending":
        return False
    item.status = "skipped"
    item.current_step = None
    item.completed_at = datetime.utcnow()
    item.error_message = "Skipped by user."
    db.add(item)
    db.commit()
    return True


def is_batch_running(batch_id: int) -> bool:
    thread = _active_workers.get(batch_id)
    return bool(thread and thread.is_alive())
