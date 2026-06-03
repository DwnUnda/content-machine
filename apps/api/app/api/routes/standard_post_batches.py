from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.entities import StandardPostBatch, StandardPostBatchItem
from app.repositories.crud import CRUDRepository
from app.schemas.standard_post_batches import (
    StandardPostBatchCounts,
    StandardPostBatchCreate,
    StandardPostBatchDetail,
    StandardPostBatchSummary,
)
from app.services.keyword_parser import parse_keywords, slugify
from app.services import standard_post_queue


router = APIRouter()
repo = CRUDRepository(StandardPostBatch)


def _counts(batch: StandardPostBatch) -> StandardPostBatchCounts:
    counts = StandardPostBatchCounts(total=len(batch.items))
    for item in batch.items:
        if item.status == "pending":
            counts.pending += 1
        elif item.status == "running":
            counts.running += 1
        elif item.status == "complete":
            counts.complete += 1
        elif item.status == "failed":
            counts.failed += 1
        elif item.status == "skipped":
            counts.skipped += 1
        elif item.status == "cancelled":
            counts.cancelled += 1
    return counts


def _summary(batch: StandardPostBatch) -> StandardPostBatchSummary:
    base = StandardPostBatchSummary.model_validate(batch)
    base.counts = _counts(batch)
    base.is_running = standard_post_queue.is_batch_running(batch.id)
    return base


def _detail(batch: StandardPostBatch) -> StandardPostBatchDetail:
    detail = StandardPostBatchDetail.model_validate(batch)
    detail.counts = _counts(batch)
    detail.is_running = standard_post_queue.is_batch_running(batch.id)
    return detail


def _get_batch_or_404(db: Session, batch_id: int) -> StandardPostBatch:
    batch = db.scalar(
        select(StandardPostBatch)
        .where(StandardPostBatch.id == batch_id)
        .options(selectinload(StandardPostBatch.items))
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Standard post batch not found")
    return batch


@router.get("", response_model=list[StandardPostBatchSummary])
def list_batches(db: Session = Depends(get_db)) -> list[StandardPostBatchSummary]:
    batches = db.scalars(
        select(StandardPostBatch)
        .options(selectinload(StandardPostBatch.items))
        .order_by(desc(StandardPostBatch.created_at))
    ).all()
    return [_summary(batch) for batch in batches]


@router.post("", response_model=StandardPostBatchDetail, status_code=status.HTTP_201_CREATED)
def create_batch(payload: StandardPostBatchCreate, db: Session = Depends(get_db)) -> StandardPostBatchDetail:
    keywords = parse_keywords(payload.keywords)
    if not keywords:
        raise HTTPException(status_code=400, detail="No valid keywords found.")

    wordpress_mode = payload.wordpress_mode if payload.wordpress_mode in {"local_only", "local_plus_draft"} else "local_only"

    batch = StandardPostBatch(
        name=payload.name,
        status="pending",  # never auto-start
        wordpress_mode=wordpress_mode,
        summary_message=f"{len(keywords)} keyword(s) queued. Click Start to begin.",
    )
    for position, keyword in enumerate(keywords):
        batch.items.append(
            StandardPostBatchItem(
                keyword=keyword,
                slug=slugify(keyword),
                position=position,
                status="pending",
            )
        )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return _detail(batch)


@router.get("/{batch_id}", response_model=StandardPostBatchDetail)
def get_batch(batch_id: int, db: Session = Depends(get_db)) -> StandardPostBatchDetail:
    return _detail(_get_batch_or_404(db, batch_id))


@router.post("/{batch_id}/start", response_model=StandardPostBatchDetail)
def start_batch(batch_id: int, db: Session = Depends(get_db)) -> StandardPostBatchDetail:
    batch = _get_batch_or_404(db, batch_id)
    if batch.status in {"running"} and standard_post_queue.is_batch_running(batch.id):
        raise HTTPException(status_code=409, detail="Batch is already running.")
    standard_post_queue.start_batch(db, batch)
    db.refresh(batch)
    return _detail(batch)


@router.post("/{batch_id}/pause", response_model=StandardPostBatchDetail)
def pause_batch(batch_id: int, db: Session = Depends(get_db)) -> StandardPostBatchDetail:
    batch = _get_batch_or_404(db, batch_id)
    standard_post_queue.request_pause(db, batch)
    db.refresh(batch)
    return _detail(batch)


@router.post("/{batch_id}/resume", response_model=StandardPostBatchDetail)
def resume_batch(batch_id: int, db: Session = Depends(get_db)) -> StandardPostBatchDetail:
    batch = _get_batch_or_404(db, batch_id)
    standard_post_queue.resume_batch(db, batch)
    db.refresh(batch)
    return _detail(batch)


@router.post("/{batch_id}/cancel", response_model=StandardPostBatchDetail)
def cancel_batch(batch_id: int, db: Session = Depends(get_db)) -> StandardPostBatchDetail:
    batch = _get_batch_or_404(db, batch_id)
    standard_post_queue.request_cancel(db, batch)
    db.refresh(batch)
    return _detail(batch)


def _get_item_or_404(db: Session, batch_id: int, item_id: int) -> StandardPostBatchItem:
    item = db.scalar(
        select(StandardPostBatchItem).where(
            StandardPostBatchItem.id == item_id,
            StandardPostBatchItem.batch_id == batch_id,
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Batch item not found")
    return item


@router.post("/{batch_id}/items/{item_id}/retry", response_model=StandardPostBatchDetail)
def retry_item(batch_id: int, item_id: int, db: Session = Depends(get_db)) -> StandardPostBatchDetail:
    batch = _get_batch_or_404(db, batch_id)
    item = _get_item_or_404(db, batch_id, item_id)
    if not standard_post_queue.retry_item(db, batch, item):
        raise HTTPException(status_code=400, detail="Item cannot be retried in its current state.")
    db.refresh(batch)
    return _detail(batch)


@router.post("/{batch_id}/items/{item_id}/skip", response_model=StandardPostBatchDetail)
def skip_item(batch_id: int, item_id: int, db: Session = Depends(get_db)) -> StandardPostBatchDetail:
    batch = _get_batch_or_404(db, batch_id)
    item = _get_item_or_404(db, batch_id, item_id)
    if not standard_post_queue.skip_item(db, item):
        raise HTTPException(status_code=400, detail="Only pending items can be skipped.")
    db.refresh(batch)
    return _detail(batch)
