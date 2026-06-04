from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import COMPLETED_ARTICLES_DIR
from app.models.entities import (
    ArticleBrief,
    ArticleDraft,
    ArticleJob,
    ArticleJobProduct,
    CompetitorAnalysisReport,
    CompetitorPage,
    ContentCluster,
    KeywordResearch,
    Product,
    ProductCandidate,
    QaReport,
    SerpResult,
    Source,
    AppLog,
    WorkflowRun,
)


def _slugify(value: str | None, fallback: str) -> str:
    text = (value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug or fallback


def _timestamp_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize(obj) -> dict:
    if obj is None:
        return {}
    mapper = inspect(obj, raiseerr=False)
    if mapper is None or not hasattr(mapper, "mapper"):
        if isinstance(obj, dict):
            return {
                key: _timestamp_value(value)
                for key, value in obj.items()
            }
        return {"value": _timestamp_value(obj)}
    data: dict[str, object] = {}
    for column in mapper.mapper.column_attrs:
        key = column.key
        value = getattr(obj, key, None)
        if isinstance(value, datetime):
            data[key] = value.isoformat()
        elif isinstance(value, dict):
            data[key] = value
        elif isinstance(value, list):
            data[key] = [_timestamp_value(item) for item in value]
        else:
            data[key] = value
    return data


def _serialize_product(product: Product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "brand": product.brand,
        "category": product.category,
        "product_url": product.product_url,
        "personally_tested": product.personally_tested,
        "model_number": product.model_number,
        "retailer_domain": product.retailer_domain,
        "price_text": product.price_text,
        "capacity_text": product.capacity_text,
        "tank_size_text": product.tank_size_text,
        "noise_level_text": product.noise_level_text,
        "power_use_text": product.power_use_text,
        "warranty_text": product.warranty_text,
        "drainage_text": product.drainage_text,
        "room_size_text": product.room_size_text,
        "review_rating_text": product.review_rating_text,
        "review_count_text": product.review_count_text,
        "description_snippet": product.description_snippet,
        "visible_specs_table": product.visible_specs_table,
        "confidence_level": product.confidence_level,
        "confidence_score": product.confidence_score,
        "common_positives": product.common_positives,
        "common_complaints": product.common_complaints,
        "who_should_buy": product.who_should_buy,
        "who_should_avoid": product.who_should_avoid,
        "best_for": product.best_for,
        "bottom_line": product.bottom_line,
        "extraction_status": product.extraction_status,
        "extraction_error": product.extraction_error,
        "raw_extracted_json": product.raw_extracted_json,
        "notes": product.notes,
        "key_drawback": product.key_drawback,
    }


def _latest_log_payload(logs: list[AppLog], event_type: str) -> dict | None:
    for log in logs:
        if log.event_type == event_type and isinstance(log.metadata_json, dict):
            return _serialize(log)
    return None


def _serialize_cluster(cluster: ContentCluster) -> dict:
    return {
        "id": cluster.id,
        "name": cluster.name,
        "description": cluster.description,
        "target_url_slug": cluster.target_url_slug,
        "notes": cluster.notes,
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_text(path: Path, payload: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload or "", encoding="utf-8")


def _generate_html_from_latest_draft(root: Path, latest_draft: dict, raise_on_error: bool = False) -> Path | None:
    """
    Generate HTML file from latest draft using the Node.js markdown converter.
    Returns the path to the generated HTML file, or None if generation failed.
    If raise_on_error is True, raises exceptions instead of returning None.
    """
    if not latest_draft or not latest_draft.get("draft_markdown"):
        if raise_on_error:
            raise ValueError("No draft_markdown found in latest_draft")
        return None

    slug = latest_draft.get("slug")
    if not slug:
        if raise_on_error:
            raise ValueError("No slug found in latest_draft")
        return None

    # Get repository root (4 levels up from apps/api/app/services)
    repo_root = Path(__file__).resolve().parents[4]
    converter_script = repo_root / "scripts" / "article-html-renderer.js"

    if not converter_script.exists():
        if raise_on_error:
            raise FileNotFoundError(f"Article HTML renderer script not found: {converter_script}")
        # If converter script doesn't exist, skip HTML generation silently
        return None

    # Create a temporary script to generate HTML
    # Use absolute path to the converter script
    converter_script_abs = str(converter_script.resolve()).replace('\\', '\\\\')

    temp_script_content = f"""
const {{ renderArticleHtml }} = require('{converter_script_abs}');
const fs = require('fs');
const path = require('path');

const latestJsonPath = process.argv[2];
const outputHtmlPath = process.argv[3];

try {{
    const jsonData = JSON.parse(fs.readFileSync(latestJsonPath, 'utf8'));
    const markdown = jsonData.draft_markdown;
    const articleJsonPath = path.resolve(path.dirname(latestJsonPath), '..', 'article.json');
    let articleData = {{}};
    if (fs.existsSync(articleJsonPath)) {{
        articleData = JSON.parse(fs.readFileSync(articleJsonPath, 'utf8'));
    }}

    if (!markdown) {{
        console.error('No draft_markdown found in JSON');
        process.exit(1);
    }}

    // Use the shared renderer so generated HTML drafts skip markdown conversion
    // and keep the same class normalization as the WordPress upload path.
    const html = renderArticleHtml(markdown, {{
        post_type: jsonData.post_type || articleData.post_type || 'informational_blog',
        content_modules: jsonData.content_modules || [],
    }});
    fs.writeFileSync(outputHtmlPath, html, 'utf8');
    console.log('HTML generated successfully');
    process.exit(0);
}} catch (error) {{
    console.error('HTML generation failed:', error.message);
    process.exit(1);
}}
"""

    # Write temporary converter script
    temp_script = repo_root / "scripts" / "_temp_html_converter.js"
    temp_script.write_text(temp_script_content, encoding="utf-8")

    try:
        latest_json_path = root / "drafts" / "latest.json"
        html_filename = f"{slug}.html"
        html_path = root / html_filename

        # Run Node.js script to generate HTML
        result = subprocess.run(
            ["node", str(temp_script), str(latest_json_path), str(html_path)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(repo_root),
        )

        if result.returncode == 0 and html_path.exists():
            return html_path
        else:
            # HTML generation failed - log the error
            error_output = result.stderr or result.stdout or "Unknown error"
            if raise_on_error:
                raise RuntimeError(f"Node.js HTML conversion failed: {error_output}")
            print(f"HTML generation failed for {slug}: {error_output}")
            return None

    except subprocess.TimeoutExpired as e:
        if raise_on_error:
            raise RuntimeError(f"HTML generation timed out after 30 seconds") from e
        print(f"HTML generation timeout for {slug}")
        return None
    except Exception as e:
        if raise_on_error:
            raise
        # If HTML generation fails, log and continue without it
        print(f"HTML generation exception for {slug}: {str(e)}")
        return None
    finally:
        # Clean up temporary script
        if temp_script.exists():
            temp_script.unlink()


def get_article_export_root(job: ArticleJob) -> Path:
    return (COMPLETED_ARTICLES_DIR / "articles" / f"article-{job.id}-{_slugify(job.title, f'article-{job.id}')}")


def get_product_export_root(product: Product) -> Path:
    return COMPLETED_ARTICLES_DIR / "products" / f"product-{product.id}-{_slugify(product.name, f'product-{product.id}')}"


def get_cluster_export_root(cluster: ContentCluster) -> Path:
    return COMPLETED_ARTICLES_DIR / "clusters" / f"cluster-{cluster.id}-{_slugify(cluster.name, f'cluster-{cluster.id}')}"


def _article_payload(db: Session, job: ArticleJob) -> dict:
    db.refresh(job)
    serp_results = list(
        db.scalars(
            select(SerpResult)
            .where(SerpResult.article_job_id == job.id)
            .order_by(SerpResult.created_at.desc(), SerpResult.position.asc())
        ).all()
    )
    keyword_research = list(
        db.scalars(
            select(KeywordResearch)
            .where(KeywordResearch.article_job_id == job.id)
            .order_by(KeywordResearch.created_at.desc())
        ).all()
    )
    competitor_pages = list(
        db.scalars(
            select(CompetitorPage)
            .where(CompetitorPage.article_job_id == job.id)
            .order_by(CompetitorPage.created_at.desc())
        ).all()
    )
    briefs = list(
        db.scalars(
            select(ArticleBrief)
            .where(ArticleBrief.article_job_id == job.id)
            .order_by(ArticleBrief.version.desc(), ArticleBrief.created_at.desc())
        ).all()
    )
    drafts = list(
        db.scalars(
            select(ArticleDraft)
            .where(ArticleDraft.article_job_id == job.id)
            .order_by(ArticleDraft.version.desc(), ArticleDraft.created_at.desc())
        ).all()
    )
    analysis_reports = list(
        db.scalars(
            select(CompetitorAnalysisReport)
            .where(CompetitorAnalysisReport.article_job_id == job.id)
            .order_by(CompetitorAnalysisReport.created_at.desc())
        ).all()
    )
    qa_reports = list(
        db.scalars(
            select(QaReport)
            .where(QaReport.article_job_id == job.id)
            .order_by(QaReport.created_at.desc(), QaReport.id.desc())
        ).all()
    )
    workflow_runs = list(
        db.scalars(
            select(WorkflowRun)
            .where(WorkflowRun.article_job_id == job.id)
            .options(selectinload(WorkflowRun.steps))
            .order_by(WorkflowRun.created_at.desc())
        ).all()
    )
    article_product_links = list(
        db.scalars(
            select(ArticleJobProduct)
            .where(ArticleJobProduct.article_job_id == job.id)
            .options(selectinload(ArticleJobProduct.product))
            .order_by(ArticleJobProduct.created_at.desc())
        ).all()
    )
    product_candidates = list(
        db.scalars(
            select(ProductCandidate)
            .where(ProductCandidate.article_job_id == job.id)
            .order_by(ProductCandidate.created_at.desc())
        ).all()
    )
    sources = list(
        db.scalars(
            select(Source)
            .where(Source.article_job_id == job.id)
            .order_by(Source.created_at.desc())
        ).all()
    )
    logs = list(
        db.scalars(
            select(AppLog)
            .where(AppLog.article_job_id == job.id)
            .order_by(AppLog.created_at.desc())
        ).all()
    )

    latest_brief = briefs[0] if briefs else None
    latest_draft = drafts[0] if drafts else None
    latest_analysis = analysis_reports[0] if analysis_reports else None
    latest_qa = qa_reports[0] if qa_reports else None
    latest_run = workflow_runs[0] if workflow_runs else None
    latest_reddit_feedback = _latest_log_payload(logs, "workflow.reddit_feedback.completed")

    return {
        "article": {
            "id": job.id,
            "title": job.title,
            "primary_keyword": job.primary_keyword,
            "post_type": job.post_type,
            "status": job.status,
            "target_audience": job.target_audience,
            "australian_angle": job.australian_angle,
            "notes": job.notes,
            "review_override": job.review_override,
            "current_qa_score": job.current_qa_score,
            "local_export_path": str(get_article_export_root(job).resolve()),
        },
        "serp_results": [_serialize(row) for row in serp_results],
        "keyword_research": [_serialize(row) for row in keyword_research],
        "reddit_feedback": latest_reddit_feedback,
        "competitor_pages": [_serialize(row) for row in competitor_pages],
        "briefs": [
            {
                "version": brief.version,
                "created_at": _timestamp_value(brief.created_at),
                "updated_at": _timestamp_value(brief.updated_at),
                "brief_markdown": brief.brief_markdown,
                "outline_json": brief.outline_json,
            }
            for brief in briefs
        ],
        "latest_brief": {
            "version": latest_brief.version if latest_brief else None,
            "brief_markdown": latest_brief.brief_markdown if latest_brief else None,
            "outline_json": latest_brief.outline_json if latest_brief else None,
        },
        "drafts": [
            {
                "version": draft.version,
                "stage": draft.stage,
                "draft_markdown": draft.draft_markdown,
                "seo_title": draft.seo_title,
                "meta_description": draft.meta_description,
                "slug": draft.slug,
                "excerpt": draft.excerpt,
                "model_name": draft.model_name,
                "prompt_name": draft.prompt_name,
                "source_payload_json": draft.source_payload_json,
                "content_modules": (draft.source_payload_json or {}).get("content_modules") if isinstance(draft.source_payload_json, dict) else None,
                "created_at": _timestamp_value(draft.created_at),
                "updated_at": _timestamp_value(draft.updated_at),
            }
            for draft in drafts
        ],
        "latest_draft": {
            "version": latest_draft.version if latest_draft else None,
            "stage": latest_draft.stage if latest_draft else None,
            "draft_markdown": latest_draft.draft_markdown if latest_draft else None,
            "seo_title": latest_draft.seo_title if latest_draft else None,
            "meta_description": latest_draft.meta_description if latest_draft else None,
            "slug": latest_draft.slug if latest_draft else None,
            "excerpt": latest_draft.excerpt if latest_draft else None,
            "content_modules": (
                (latest_draft.source_payload_json or {}).get("content_modules")
                if latest_draft and isinstance(latest_draft.source_payload_json, dict)
                else None
            ),
            # Preserve the article's primary/focus keyword in the export so the
            # WordPress uploader can pass it through as the Rank Math focus keyword.
            "primary_keyword": job.primary_keyword,
        },
        "serp_analysis_reports": [_serialize(row) for row in analysis_reports],
        "qa_reports": [_serialize(row) for row in qa_reports],
        "latest_serp_analysis": _serialize(latest_analysis) if latest_analysis else None,
        "latest_qa": _serialize(latest_qa) if latest_qa else None,
        "workflow_runs": [
            {
                "id": run.id,
                "workflow_mode": run.workflow_mode,
                "research_mode": run.research_mode,
                "status": run.status,
                "current_step": run.current_step,
                "summary_message": run.summary_message,
                "created_at": _timestamp_value(run.created_at),
                "updated_at": _timestamp_value(run.updated_at),
                "steps": [
                    {
                        "id": step.id,
                        "step_key": step.step_key,
                        "step_label": step.step_label,
                        "status": step.status,
                        "message": step.message,
                    }
                    for step in run.steps
                ],
            }
            for run in workflow_runs
        ],
        "latest_workflow_run": {
            "id": latest_run.id if latest_run else None,
            "workflow_mode": latest_run.workflow_mode if latest_run else None,
            "research_mode": latest_run.research_mode if latest_run else None,
            "status": latest_run.status if latest_run else None,
            "current_step": latest_run.current_step if latest_run else None,
            "summary_message": latest_run.summary_message if latest_run else None,
        },
        "article_product_links": [
            {
                "id": link.id,
                "source_url": link.source_url,
                "original_source_url": link.original_source_url,
                "cleaned_source_url": link.cleaned_source_url,
                "source_type": link.source_type,
                "extraction_status": link.extraction_status,
                "extraction_error": link.extraction_error,
                "draft_ready": link.draft_ready,
                "readiness_status": link.readiness_status,
                "missing_fields": link.missing_fields,
                "retailer": link.retailer,
                "key_drawback": link.key_drawback,
                "product": _serialize_product(link.product) if link.product else None,
            }
            for link in article_product_links
        ],
        "product_candidates": [_serialize(candidate) for candidate in product_candidates],
        "sources": [_serialize(source) for source in sources],
        "app_logs": [_serialize(log) for log in logs],
    }


def sync_article_export(db: Session, job: ArticleJob | int, *, reason: str | None = None) -> Path:
    job_obj = job if isinstance(job, ArticleJob) else db.get(ArticleJob, job)
    if not job_obj:
        raise ValueError("Article job not found")

    payload = _article_payload(db, job_obj)
    root = get_article_export_root(job_obj)
    root.mkdir(parents=True, exist_ok=True)

    _write_json(root / "article.json", payload["article"])
    _write_json(root / "manifest.json", {"reason": reason, "exported_at": datetime.utcnow().isoformat(), "article": payload["article"]})
    _write_json(root / "research" / "serp-results.json", payload["serp_results"])
    _write_json(root / "research" / "keyword-research.json", payload["keyword_research"])
    _write_json(root / "research" / "reddit-feedback.json", payload["reddit_feedback"])
    _write_json(root / "research" / "competitor-pages.json", payload["competitor_pages"])
    _write_json(root / "research" / "serp-analysis.json", payload["latest_serp_analysis"])

    for brief in payload["briefs"]:
        version = brief["version"] or 0
        _write_json(root / "briefs" / f"brief-v{version}.json", brief)
        _write_text(root / "briefs" / f"brief-v{version}.md", brief.get("brief_markdown"))
    _write_json(root / "briefs" / "latest.json", payload["latest_brief"])
    _write_text(root / "briefs" / "latest.md", payload["latest_brief"].get("brief_markdown") if payload["latest_brief"] else "")

    for draft in payload["drafts"]:
        version = draft["version"] or 0
        stage = draft["stage"] or "draft"
        _write_json(root / "drafts" / f"draft-v{version}-{stage}.json", draft)
        _write_text(root / "drafts" / f"draft-v{version}-{stage}.md", draft.get("draft_markdown"))
    _write_json(root / "drafts" / "latest.json", payload["latest_draft"])
    _write_text(root / "drafts" / "latest.md", payload["latest_draft"].get("draft_markdown") if payload["latest_draft"] else "")

    # Generate HTML from latest draft
    _generate_html_from_latest_draft(root, payload["latest_draft"])

    _write_json(root / "qa" / "latest.json", payload["latest_qa"])
    _write_json(root / "qa" / "all.json", payload["qa_reports"])
    _write_json(root / "workflow" / "latest.json", payload["latest_workflow_run"])
    _write_json(root / "workflow" / "all.json", payload["workflow_runs"])
    _write_json(root / "products" / "linked-products.json", payload["article_product_links"])
    _write_json(root / "products" / "candidates.json", payload["product_candidates"])
    _write_json(root / "sources" / "sources.json", payload["sources"])
    _write_json(root / "logs" / "app-logs.json", payload["app_logs"])
    _write_json(root / "overview.json", payload)
    return root


def export_product_record(db: Session, product: Product | int, *, reason: str | None = None) -> Path:
    product_obj = product if isinstance(product, Product) else db.get(Product, product)
    if not product_obj:
        raise ValueError("Product not found")

    root = get_product_export_root(product_obj)
    root.mkdir(parents=True, exist_ok=True)
    payload = _serialize_product(product_obj)
    payload["reason"] = reason
    _write_json(root / "product.json", payload)
    _write_json(root / "manifest.json", {"reason": reason, "exported_at": datetime.utcnow().isoformat(), "product_id": product_obj.id})
    return root


def export_cluster_record(db: Session, cluster: ContentCluster | int, *, reason: str | None = None) -> Path:
    cluster_obj = cluster if isinstance(cluster, ContentCluster) else db.get(ContentCluster, cluster)
    if not cluster_obj:
        raise ValueError("Cluster not found")

    root = get_cluster_export_root(cluster_obj)
    root.mkdir(parents=True, exist_ok=True)
    payload = _serialize_cluster(cluster_obj)
    payload["reason"] = reason
    _write_json(root / "cluster.json", payload)
    _write_json(root / "manifest.json", {"reason": reason, "exported_at": datetime.utcnow().isoformat(), "cluster_id": cluster_obj.id})
    return root
