from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Source
from app.repositories.crud import CRUDRepository
from app.schemas.sources import SourceCreate, SourceResponse, SourceUpdate


router = APIRouter()
repo = CRUDRepository(Source)


@router.get("", response_model=list[SourceResponse])
def list_sources(db: Session = Depends(get_db)) -> list[Source]:
    return repo.list(db)


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceCreate, db: Session = Depends(get_db)) -> Source:
    return repo.create(db, payload.model_dump())


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(source_id: int, db: Session = Depends(get_db)) -> Source:
    source = repo.get(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.put("/{source_id}", response_model=SourceResponse)
def update_source(source_id: int, payload: SourceUpdate, db: Session = Depends(get_db)) -> Source:
    source = repo.get(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return repo.update(db, source, payload.model_dump(exclude_none=True))


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: int, db: Session = Depends(get_db)) -> None:
    source = repo.get(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    repo.delete(db, source)

