import shutil

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, desc, select, update
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.entities import (
    AppLog,
    ArticleBrief,
    ArticleDraft,
    ArticleJob,
    ArticleJobProduct,
    CompetitorAnalysisReport,
    CompetitorPage,
    InternalLink,
    KeywordResearch,
    ProductCandidate,
    ProductSource,
    QaReport,
    SerpResult,
    Source,
    StandardPostBatchItem,
    WordPressExport,
    WorkflowRun,
    WorkflowRunStep,
)
from app.repositories.crud import CRUDRepository
from app.schemas.article_jobs import ArticleJobCreate, ArticleJobDetail, ArticleJobSummary, ArticleJobUpdate, EditorCorrectionRequest, WorkflowActionResponse
from app.schemas.briefs import ArticleBriefListResponse, ArticleBriefResponse, ArticleBriefUpdateRequest
from app.schemas.competitors import CompetitorAnalysisReportResponse, CompetitorPagesListResponse
from app.schemas.drafts import ArticleDraftListResponse, ArticleDraftResponse
from app.schemas.product_candidates import ConvertProductCandidateRequest, ProductCandidateConversionResponse, ProductCandidatesListResponse
from app.schemas.qa_reports import QaReportListResponse, QaReportResponse
from app.schemas.product_research import ArticleJobProductResponse, ArticleJobProductsListResponse, ArticleJobProductSourceCreate, ExtractProductRequest
from app.schemas.recovery import ArticleRecoveryRequest
from app.schemas.research import KeywordResearchListResponse, SerpResultsListResponse
from app.schemas.workflow_runs import FullWorkflowRequest, WorkflowRunResponse, WorkflowStateResponse
from app.services.article_recovery import ArticleRecoveryError, restore_article_from_export
from app.services.anthropic_client import AnthropicError
from app.services.article_drafting import ArticleDraftingError, apply_editor_corrections
from app.services.article_drafting import list_article_drafts, list_qa_reports
from app.core.config import get_settings
from app.services.dataforseo import DataForSEOError
from app.services import local_exports
from app.services.local_exports import sync_article_export
from app.services.logging import create_app_log
from app.services.product_research import (
    ProductResearchError,
    approve_product_draft_ready,
    create_article_product_source,
    extract_product_for_link,
    research_product_for_link,
    research_product_via_websearch,
)
from app.services.product_candidates import ProductCandidateError, list_product_candidates
from app.services.openai_client import OpenAIError
from app.services import workflow as workflow_service


router = APIRouter()
repo = CRUDRepository(ArticleJob)


def _delete_local_article_export(job: ArticleJob) -> None:
    export_root = local_exports.get_article_export_root(job).resolve()
    articles_root = (local_exports.COMPLETED_ARTICLES_DIR / "articles").resolve()
    if not export_root.exists():
        return
    if not export_root.is_relative_to(articles_root):
        return
    if not export_root.name.startswith(f"article-{job.id}-"):
        return
    shutil.rmtree(export_root, ignore_errors=True)


def _delete_article_job_records(db: Session, job_id: int) -> None:
    source_ids = list(db.scalars(select(Source.id).where(Source.article_job_id == job_id)).all())
    if source_ids:
        db.execute(delete(ProductSource).where(ProductSource.source_id.in_(source_ids)))

    workflow_run_ids = list(db.scalars(select(WorkflowRun.id).where(WorkflowRun.article_job_id == job_id)).all())
    if workflow_run_ids:
        db.execute(delete(WorkflowRunStep).where(WorkflowRunStep.workflow_run_id.in_(workflow_run_ids)))

    db.execute(update(StandardPostBatchItem).where(StandardPostBatchItem.article_job_id == job_id).values(article_job_id=None))

    for model in (
        AppLog,
        WordPressExport,
        InternalLink,
        QaReport,
        ArticleDraft,
        ArticleBrief,
        WorkflowRun,
        ArticleJobProduct,
        ProductCandidate,
        CompetitorAnalysisReport,
        CompetitorPage,
        KeywordResearch,
        SerpResult,
        Source,
    ):
        db.execute(delete(model).where(model.article_job_id == job_id))


@router.get("", response_model=list[ArticleJobSummary])
def list_article_jobs(db: Session = Depends(get_db)) -> list[ArticleJob]:
    return repo.list(db)


@router.post("", response_model=ArticleJobSummary, status_code=status.HTTP_201_CREATED)
def create_article_job(payload: ArticleJobCreate, db: Session = Depends(get_db)) -> ArticleJob:
    job = repo.create(db, {**payload.model_dump(), "status": "New"})
    create_app_log(
        db,
        event_type="article_job.created",
        message=f"Article job '{job.title}' created.",
        article_job_id=job.id,
    )
    sync_article_export(db, job, reason="article_created")
    return job


@router.post("/recover-from-export", response_model=ArticleJobSummary, status_code=status.HTTP_201_CREATED)
def recover_article_job(payload: ArticleRecoveryRequest, db: Session = Depends(get_db)) -> ArticleJob:
    try:
        job = restore_article_from_export(db, payload.bundle_path)
    except ArticleRecoveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job


@router.get("/{job_id}", response_model=ArticleJobDetail)
def get_article_job(job_id: int, db: Session = Depends(get_db)) -> ArticleJob:
    query = (
        select(ArticleJob)
        .where(ArticleJob.id == job_id)
        .options(
            selectinload(ArticleJob.serp_results),
            selectinload(ArticleJob.keyword_research),
            selectinload(ArticleJob.competitor_pages),
            selectinload(ArticleJob.sources),
            selectinload(ArticleJob.briefs),
            selectinload(ArticleJob.drafts),
            selectinload(ArticleJob.qa_reports),
            selectinload(ArticleJob.wordpress_exports),
            selectinload(ArticleJob.internal_links),
        )
    )
    job = db.scalar(query)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    return job


@router.put("/{job_id}", response_model=ArticleJobSummary)
def update_article_job(job_id: int, payload: ArticleJobUpdate, db: Session = Depends(get_db)) -> ArticleJob:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    updated = repo.update(db, job, payload.model_dump(exclude_none=True))
    sync_article_export(db, updated, reason="article_updated")
    return updated


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article_job(job_id: int, db: Session = Depends(get_db)) -> None:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    _delete_local_article_export(job)
    _delete_article_job_records(db, job_id)
    db.delete(job)
    db.commit()


@router.post("/{job_id}/run-serp-research")
def run_serp_research(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    try:
        return workflow_service.run_serp_research(db, job)
    except DataForSEOError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/{job_id}/run-keyword-research")
def run_keyword_research(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    try:
        return workflow_service.run_keyword_research(db, job)
    except DataForSEOError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{job_id}/serp-results", response_model=SerpResultsListResponse)
def get_serp_results(job_id: int, db: Session = Depends(get_db)) -> SerpResultsListResponse:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    items = list(
        db.scalars(
            select(SerpResult)
            .where(SerpResult.article_job_id == job_id)
            .order_by(desc(SerpResult.created_at), SerpResult.position.asc())
        ).all()
    )
    return SerpResultsListResponse(items=items)


@router.get("/{job_id}/keyword-research", response_model=KeywordResearchListResponse)
def get_keyword_research(job_id: int, db: Session = Depends(get_db)) -> KeywordResearchListResponse:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    items = list(
        db.scalars(
            select(KeywordResearch)
            .where(KeywordResearch.article_job_id == job_id)
            .order_by(desc(KeywordResearch.created_at))
        ).all()
    )
    return KeywordResearchListResponse(items=items)


@router.post("/{job_id}/extract-competitors")
def extract_competitors(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    try:
        return workflow_service.extract_competitors(db, job)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Competitor extraction failed.") from exc


@router.post("/{job_id}/analyse-serp")
def analyse_serp(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    try:
        return workflow_service.analyse_serp(db, job)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="SERP analysis failed.") from exc


@router.get("/{job_id}/competitor-pages", response_model=CompetitorPagesListResponse)
def get_competitor_pages(job_id: int, db: Session = Depends(get_db)) -> CompetitorPagesListResponse:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    items = list(
        db.scalars(
            select(CompetitorPage)
            .where(CompetitorPage.article_job_id == job_id)
            .order_by(desc(CompetitorPage.created_at))
        ).all()
    )
    return CompetitorPagesListResponse(items=items)


@router.get("/{job_id}/serp-analysis", response_model=CompetitorAnalysisReportResponse | None)
def get_serp_analysis(job_id: int, db: Session = Depends(get_db)) -> CompetitorAnalysisReportResponse | None:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    report = db.scalar(
        select(CompetitorAnalysisReport)
        .where(CompetitorAnalysisReport.article_job_id == job_id)
        .order_by(desc(CompetitorAnalysisReport.created_at))
    )
    return report


@router.post("/{job_id}/generate-research-brief")
def generate_research_brief(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    return workflow_service.generate_brief(db, job)


@router.post("/{job_id}/generate-draft", response_model=WorkflowActionResponse)
def generate_draft(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    try:
        return workflow_service.generate_draft(db, job)
    except ArticleDraftingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (AnthropicError, OpenAIError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/{job_id}/run-human-edit", response_model=WorkflowActionResponse)
def run_human_edit(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    try:
        return workflow_service.run_australian_human_rewrite(db, job)
    except ArticleDraftingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (AnthropicError, OpenAIError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/{job_id}/run-qa", response_model=WorkflowActionResponse)
def run_qa(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    try:
        return workflow_service.run_qa(db, job, stage="initial")
    except ArticleDraftingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (AnthropicError, OpenAIError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/{job_id}/run-fix-pass", response_model=WorkflowActionResponse)
def run_fix_pass(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    try:
        return workflow_service.run_fix_pass(db, job)
    except ArticleDraftingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (AnthropicError, OpenAIError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/{job_id}/apply-editor-corrections", response_model=WorkflowActionResponse)
def apply_editor_correction_notes(job_id: int, payload: EditorCorrectionRequest, db: Session = Depends(get_db)) -> dict:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    try:
        result = apply_editor_corrections(db, job, payload.correction_notes)
    except ArticleDraftingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (AnthropicError, OpenAIError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    sync_article_export(db, job, reason="editor_corrections")
    return result


@router.get("/{job_id}/briefs", response_model=ArticleBriefListResponse)
def get_article_briefs(job_id: int, db: Session = Depends(get_db)) -> ArticleBriefListResponse:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    items = list(
        db.scalars(
            select(ArticleBrief)
            .where(ArticleBrief.article_job_id == job_id)
            .order_by(desc(ArticleBrief.created_at))
        ).all()
    )
    return ArticleBriefListResponse(items=items)


@router.get("/{job_id}/drafts", response_model=ArticleDraftListResponse)
def get_article_drafts(job_id: int, db: Session = Depends(get_db)) -> ArticleDraftListResponse:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    return ArticleDraftListResponse(items=list_article_drafts(db, job_id))


@router.get("/{job_id}/qa-reports", response_model=QaReportListResponse)
def get_article_qa_reports(job_id: int, db: Session = Depends(get_db)) -> QaReportListResponse:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    return QaReportListResponse(items=list_qa_reports(db, job_id))


@router.put("/briefs/{brief_id}", response_model=ArticleBriefResponse)
def update_article_brief(brief_id: int, payload: ArticleBriefUpdateRequest, db: Session = Depends(get_db)) -> ArticleBrief:
    brief = db.get(ArticleBrief, brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Article brief not found")
    brief.brief_markdown = payload.brief_markdown
    db.add(brief)
    db.commit()
    db.refresh(brief)
    create_app_log(
        db,
        event_type="article_brief.updated",
        message="Research brief updated manually.",
        article_job_id=brief.article_job_id,
        metadata_json={"brief_id": brief.id},
    )
    sync_article_export(db, brief.article_job_id, reason="brief_updated")
    return brief


@router.post("/{job_id}/run-full-workflow", response_model=WorkflowRunResponse)
def run_full_workflow(job_id: int, payload: FullWorkflowRequest, db: Session = Depends(get_db)) -> WorkflowRun:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    try:
        return workflow_service.run_full_workflow(db, job, research_mode=payload.research_mode)
    except DataForSEOError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ArticleDraftingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (AnthropicError, OpenAIError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{job_id}/workflow-runs/latest", response_model=WorkflowRunResponse | None)
def get_latest_workflow_run(job_id: int, db: Session = Depends(get_db)) -> WorkflowRun | None:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    run = db.scalar(
        select(WorkflowRun)
        .where(WorkflowRun.article_job_id == job_id)
        .options(selectinload(WorkflowRun.steps))
        .order_by(desc(WorkflowRun.created_at))
    )
    return run


@router.get("/{job_id}/workflow-state", response_model=WorkflowStateResponse)
def get_workflow_state(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    return workflow_service.get_workflow_state(db, job)


@router.post("/{job_id}/product-sources", response_model=ArticleJobProductResponse, status_code=status.HTTP_201_CREATED)
def create_product_source(job_id: int, payload: ArticleJobProductSourceCreate, db: Session = Depends(get_db)) -> ArticleJobProduct:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    link = create_article_product_source(
        db,
        article_job_id=job_id,
        source_url=str(payload.source_url),
        source_type=payload.source_type,
    )
    sync_article_export(db, job_id, reason="product_source_created")
    return link


@router.post("/{job_id}/extract-product", response_model=ArticleJobProductResponse)
def extract_product(job_id: int, payload: ExtractProductRequest, db: Session = Depends(get_db)) -> ArticleJobProduct:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    link = db.scalar(
        select(ArticleJobProduct)
        .where(ArticleJobProduct.id == payload.product_source_id, ArticleJobProduct.article_job_id == job_id)
        .options(selectinload(ArticleJobProduct.product))
    )
    if not link:
        raise HTTPException(status_code=404, detail="Product source not found")
    create_app_log(
        db,
        event_type="workflow.product_extraction.started",
        message="Product extraction started.",
        article_job_id=job_id,
        metadata_json={"product_source_id": link.id, "source_url": link.source_url, "source_type": link.source_type},
    )
    result = extract_product_for_link(db, link)
    if result.extraction_status == "failed":
        create_app_log(
            db,
            event_type="workflow.product_extraction.failed",
            message="Product extraction failed.",
            article_job_id=job_id,
            level="ERROR",
            metadata_json={"product_source_id": result.id, "source_url": result.source_url, "error": result.extraction_error},
        )
    else:
        create_app_log(
            db,
            event_type="workflow.product_extraction.completed",
            message="Product extraction completed.",
            article_job_id=job_id,
            metadata_json={"product_source_id": result.id, "product_id": result.product_id, "source_url": result.source_url},
        )
    sync_article_export(db, job_id, reason="product_extracted")
    return db.scalar(
        select(ArticleJobProduct)
        .where(ArticleJobProduct.id == result.id)
        .options(selectinload(ArticleJobProduct.product))
    )


@router.get("/{job_id}/products", response_model=ArticleJobProductsListResponse)
def get_article_products(job_id: int, db: Session = Depends(get_db)) -> ArticleJobProductsListResponse:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    items = list(
        db.scalars(
            select(ArticleJobProduct)
            .where(ArticleJobProduct.article_job_id == job_id)
            .options(selectinload(ArticleJobProduct.product))
            .order_by(desc(ArticleJobProduct.created_at))
        ).all()
    )
    return ArticleJobProductsListResponse(items=items)


def _load_product_link(db: Session, job_id: int, link_id: int) -> ArticleJobProduct:
    link = db.scalar(
        select(ArticleJobProduct)
        .where(ArticleJobProduct.id == link_id, ArticleJobProduct.article_job_id == job_id)
        .options(selectinload(ArticleJobProduct.product))
    )
    if not link:
        raise HTTPException(status_code=404, detail="Product source not found")
    return link


@router.post("/{job_id}/products/{link_id}/research-card", response_model=ArticleJobProductResponse)
def research_product_card(job_id: int, link_id: int, db: Session = Depends(get_db)) -> ArticleJobProduct:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    link = _load_product_link(db, job_id, link_id)
    create_app_log(
        db,
        event_type="workflow.product_research.started",
        message="Product card research started.",
        article_job_id=job_id,
        metadata_json={"product_source_id": link.id, "source_url": link.source_url},
    )
    # Prefer OpenAI web-search research when configured; fall back to the
    # DataForSEO-based research path otherwise.
    use_web_search = bool(get_settings().openai_api_key)
    try:
        if use_web_search:
            result = research_product_via_websearch(db, link)
        else:
            result = research_product_for_link(db, link)
    except ProductResearchError as exc:
        create_app_log(
            db,
            event_type="workflow.product_research.failed",
            message="Product card research failed.",
            article_job_id=job_id,
            level="ERROR",
            metadata_json={"product_source_id": link.id, "error": str(exc), "web_search": use_web_search},
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    create_app_log(
        db,
        event_type="workflow.product_research.completed",
        message="Product card research completed.",
        article_job_id=job_id,
        metadata_json={"product_source_id": result.id, "product_id": result.product_id},
    )
    sync_article_export(db, job_id, reason="product_researched")
    return _load_product_link(db, job_id, result.id)


@router.post("/{job_id}/products/{link_id}/approve-draft-ready", response_model=ArticleJobProductResponse)
def approve_product_card_draft_ready(job_id: int, link_id: int, db: Session = Depends(get_db)) -> ArticleJobProduct:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    link = _load_product_link(db, job_id, link_id)
    try:
        result = approve_product_draft_ready(db, link)
    except ProductResearchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    create_app_log(
        db,
        event_type="workflow.product_card.approved_draft_ready",
        message="Product card marked draft-ready after review.",
        article_job_id=job_id,
        metadata_json={"product_source_id": result.id, "product_id": result.product_id},
    )
    sync_article_export(db, job_id, reason="product_draft_ready_approved")
    return _load_product_link(db, job_id, result.id)


@router.post("/{job_id}/find-product-candidates", response_model=WorkflowActionResponse)
def find_product_candidates(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    try:
        return workflow_service.find_product_candidates(db, job)
    except DataForSEOError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/{job_id}/auto-research-products", response_model=WorkflowActionResponse)
def auto_research_products(job_id: int, db: Session = Depends(get_db)) -> dict:
    """Manual trigger for the same automatic product step the workflow runs: research +
    verify any not-ready linked cards, and discover more via web search if below the floor."""
    job = repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Article job not found")
    create_app_log(
        db,
        event_type="workflow.product_research.manual_started",
        message="Manual AI product research/discovery started.",
        article_job_id=job_id,
    )
    try:
        result = workflow_service.run_product_research(db, job)
    except ProductResearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    sync_article_export(db, job_id, reason="auto_product_research")
    return {
        "action": "auto-research-products",
        "article_job_id": job_id,
        "status": "complete",
        "message": result["message"],
        "next_step": None,
    }


@router.get("/{job_id}/product-candidates", response_model=ProductCandidatesListResponse)
def get_product_candidates(job_id: int, db: Session = Depends(get_db)) -> ProductCandidatesListResponse:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    return ProductCandidatesListResponse(items=list_product_candidates(db, job_id))


@router.post("/{job_id}/product-candidates/{candidate_id}/approve", response_model=WorkflowActionResponse)
def approve_candidate(job_id: int, candidate_id: int, db: Session = Depends(get_db)) -> dict:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    candidate = db.scalar(select(ProductCandidate).where(ProductCandidate.id == candidate_id, ProductCandidate.article_job_id == job_id))
    if not candidate:
        raise HTTPException(status_code=404, detail="Product candidate not found")
    return workflow_service.approve_candidate(db, candidate)


@router.post("/{job_id}/product-candidates/{candidate_id}/ignore", response_model=WorkflowActionResponse)
def ignore_candidate(job_id: int, candidate_id: int, db: Session = Depends(get_db)) -> dict:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    candidate = db.scalar(select(ProductCandidate).where(ProductCandidate.id == candidate_id, ProductCandidate.article_job_id == job_id))
    if not candidate:
        raise HTTPException(status_code=404, detail="Product candidate not found")
    return workflow_service.ignore_candidate(db, candidate)


@router.post("/{job_id}/product-candidates/{candidate_id}/convert", response_model=ProductCandidateConversionResponse)
def convert_candidate(
    job_id: int,
    candidate_id: int,
    payload: ConvertProductCandidateRequest,
    db: Session = Depends(get_db),
) -> ProductCandidateConversionResponse:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    candidate = db.scalar(select(ProductCandidate).where(ProductCandidate.id == candidate_id, ProductCandidate.article_job_id == job_id))
    if not candidate:
        raise HTTPException(status_code=404, detail="Product candidate not found")
    try:
        candidate, link = workflow_service.convert_candidate(db, candidate, auto_extract=payload.auto_extract)
    except ProductCandidateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    link = db.scalar(
        select(ArticleJobProduct)
        .where(ArticleJobProduct.id == link.id)
        .options(selectinload(ArticleJobProduct.product))
    )
    return ProductCandidateConversionResponse(candidate=candidate, product_link=link)


@router.delete("/{job_id}/product-sources/{product_source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_source(job_id: int, product_source_id: int, db: Session = Depends(get_db)) -> None:
    if not repo.get(db, job_id):
        raise HTTPException(status_code=404, detail="Article job not found")
    link = db.scalar(select(ArticleJobProduct).where(ArticleJobProduct.id == product_source_id, ArticleJobProduct.article_job_id == job_id))
    if not link:
        raise HTTPException(status_code=404, detail="Product source not found")
    db.delete(link)
    db.commit()
    sync_article_export(db, job_id, reason="product_source_deleted")
