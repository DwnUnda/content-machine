from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


class CRUDRepository:
    def __init__(self, model: type):
        self.model = model

    def list(self, db: Session) -> list[Any]:
        return list(db.scalars(select(self.model).order_by(self.model.created_at.desc())).all())

    def get(self, db: Session, entity_id: int) -> Any | None:
        return db.get(self.model, entity_id)

    def create(self, db: Session, payload: dict[str, Any]) -> Any:
        entity = self.model(**payload)
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return entity

    def update(self, db: Session, entity: Any, payload: dict[str, Any]) -> Any:
        for key, value in payload.items():
            setattr(entity, key, value)
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return entity

    def delete(self, db: Session, entity: Any) -> None:
        db.delete(entity)
        db.commit()
