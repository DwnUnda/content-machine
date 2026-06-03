from sqlalchemy.orm import Session

from app.models.entities import AppLog


def create_app_log(
    db: Session,
    *,
    event_type: str,
    message: str,
    level: str = "INFO",
    article_job_id: int | None = None,
    metadata_json: dict | None = None,
) -> AppLog:
    log = AppLog(
        level=level,
        event_type=event_type,
        message=message,
        article_job_id=article_job_id,
        metadata_json=metadata_json,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log

