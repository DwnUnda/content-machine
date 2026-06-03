from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import ArticleJob
from app.schemas.article_jobs import WorkflowActionResponse
from app.schemas.content_rules import ManualReviewOverrideRequest
from app.services import workflow as workflow_service


router = APIRouter()


def _get_job_or_404(db: Session, job_id: int) -> ArticleJob:
    job = db.get(ArticleJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    return job


@router.post("/article-jobs/{job_id}/serp-research", response_model=WorkflowActionResponse)
def run_serp_research(job_id: int, db: Session = Depends(get_db)) -> dict:
    return workflow_service.run_serp_research(db, _get_job_or_404(db, job_id))


@router.post("/article-jobs/{job_id}/competitor-gap-analysis", response_model=WorkflowActionResponse)
def run_competitor_gap_analysis(job_id: int, db: Session = Depends(get_db)) -> dict:
    return workflow_service.run_competitor_gap_analysis(db, _get_job_or_404(db, job_id))


@router.post("/article-jobs/{job_id}/product-review-research", response_model=WorkflowActionResponse)
def run_product_review_research(job_id: int, db: Session = Depends(get_db)) -> dict:
    return workflow_service.run_product_review_research(db, _get_job_or_404(db, job_id))


@router.post("/article-jobs/{job_id}/serp-intent", response_model=WorkflowActionResponse)
def classify_serp_intent(job_id: int, db: Session = Depends(get_db)) -> dict:
    return workflow_service.classify_serp_intent(db, _get_job_or_404(db, job_id))


@router.post("/article-jobs/{job_id}/brief", response_model=WorkflowActionResponse)
def generate_brief(job_id: int, db: Session = Depends(get_db)) -> dict:
    return workflow_service.generate_brief(db, _get_job_or_404(db, job_id))


@router.post("/article-jobs/{job_id}/original-value-checklist", response_model=WorkflowActionResponse)
def create_original_value_checklist(job_id: int, db: Session = Depends(get_db)) -> dict:
    return workflow_service.create_original_value_checklist(db, _get_job_or_404(db, job_id))


@router.post("/article-jobs/{job_id}/draft", response_model=WorkflowActionResponse)
def generate_draft(job_id: int, db: Session = Depends(get_db)) -> dict:
    return workflow_service.generate_draft(db, _get_job_or_404(db, job_id))


@router.post("/article-jobs/{job_id}/australian-human-rewrite", response_model=WorkflowActionResponse)
def run_australian_human_rewrite(job_id: int, db: Session = Depends(get_db)) -> dict:
    return workflow_service.run_australian_human_rewrite(db, _get_job_or_404(db, job_id))


@router.post("/article-jobs/{job_id}/qa", response_model=WorkflowActionResponse)
def run_qa(job_id: int, db: Session = Depends(get_db)) -> dict:
    return workflow_service.run_qa(db, _get_job_or_404(db, job_id))


@router.post("/article-jobs/{job_id}/fix-pass", response_model=WorkflowActionResponse)
def run_fix_pass(job_id: int, db: Session = Depends(get_db)) -> dict:
    return workflow_service.run_fix_pass(db, _get_job_or_404(db, job_id))


@router.post("/article-jobs/{job_id}/manual-review-override", response_model=WorkflowActionResponse)
def set_manual_review_override(
    job_id: int,
    payload: ManualReviewOverrideRequest,
    db: Session = Depends(get_db),
) -> dict:
    return workflow_service.set_manual_review_override(db, _get_job_or_404(db, job_id), payload.enabled)


@router.post("/article-jobs/{job_id}/generate-html", response_model=WorkflowActionResponse)
def generate_html(job_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return workflow_service.generate_html_from_draft(db, _get_job_or_404(db, job_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HTML generation failed: {str(e)}")


@router.post("/article-jobs/{job_id}/wordpress-export", response_model=WorkflowActionResponse)
def export_wordpress_draft(job_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return workflow_service.export_to_wordpress_draft(db, _get_job_or_404(db, job_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"WordPress upload failed: {str(e)}")
