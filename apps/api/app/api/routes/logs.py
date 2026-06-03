from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import AppLog
from app.schemas.logs import AppLogListResponse


router = APIRouter()


@router.get("", response_model=AppLogListResponse)
def list_logs(
    article_job_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AppLogListResponse:
    query = select(AppLog).order_by(desc(AppLog.created_at))
    if article_job_id is not None:
        query = query.where(AppLog.article_job_id == article_job_id)
    return AppLogListResponse(items=list(db.scalars(query).all()))

