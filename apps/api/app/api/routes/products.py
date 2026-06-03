from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Product
from app.repositories.crud import CRUDRepository
from app.schemas.products import ProductCreate, ProductResponse, ProductUpdate
from app.services.local_exports import export_product_record, sync_article_export


router = APIRouter()
repo = CRUDRepository(Product)


@router.get("", response_model=list[ProductResponse])
def list_products(db: Session = Depends(get_db)) -> list[Product]:
    return repo.list(db)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)) -> Product:
    product = repo.create(db, payload.model_dump())
    export_product_record(db, product, reason="product_created")
    return product


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)) -> Product:
    product = repo.get(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)) -> Product:
    product = repo.get(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    updated = repo.update(db, product, payload.model_dump(exclude_none=True))
    export_product_record(db, updated, reason="product_updated")
    for link in updated.article_job_links:
        sync_article_export(db, link.article_job_id, reason="linked_product_updated")
    return updated


@router.patch("/{product_id}", response_model=ProductResponse)
def patch_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)) -> Product:
    product = repo.get(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    updated = repo.update(db, product, payload.model_dump(exclude_none=True))
    export_product_record(db, updated, reason="product_updated")
    for link in updated.article_job_links:
        sync_article_export(db, link.article_job_id, reason="linked_product_updated")
    return updated


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db)) -> None:
    product = repo.get(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    repo.delete(db, product)
