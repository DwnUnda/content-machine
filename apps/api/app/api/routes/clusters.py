from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import ContentCluster
from app.repositories.crud import CRUDRepository
from app.schemas.clusters import ContentClusterCreate, ContentClusterResponse, ContentClusterUpdate
from app.services.local_exports import export_cluster_record, sync_article_export


router = APIRouter()
repo = CRUDRepository(ContentCluster)


@router.get("", response_model=list[ContentClusterResponse])
def list_clusters(db: Session = Depends(get_db)) -> list[ContentCluster]:
    return repo.list(db)


@router.post("", response_model=ContentClusterResponse, status_code=status.HTTP_201_CREATED)
def create_cluster(payload: ContentClusterCreate, db: Session = Depends(get_db)) -> ContentCluster:
    cluster = repo.create(db, payload.model_dump())
    export_cluster_record(db, cluster, reason="cluster_created")
    return cluster


@router.get("/{cluster_id}", response_model=ContentClusterResponse)
def get_cluster(cluster_id: int, db: Session = Depends(get_db)) -> ContentCluster:
    cluster = repo.get(db, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Content cluster not found")
    return cluster


@router.put("/{cluster_id}", response_model=ContentClusterResponse)
def update_cluster(cluster_id: int, payload: ContentClusterUpdate, db: Session = Depends(get_db)) -> ContentCluster:
    cluster = repo.get(db, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Content cluster not found")
    updated = repo.update(db, cluster, payload.model_dump(exclude_none=True))
    export_cluster_record(db, updated, reason="cluster_updated")
    for article_job in updated.article_jobs:
        sync_article_export(db, article_job.id, reason="linked_cluster_updated")
    return updated


@router.delete("/{cluster_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cluster(cluster_id: int, db: Session = Depends(get_db)) -> None:
    cluster = repo.get(db, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Content cluster not found")
    repo.delete(db, cluster)
