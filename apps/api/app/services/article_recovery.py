from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import COMPLETED_ARTICLES_DIR
from app.models.entities import (
    AppLog,
    ArticleBrief,
    ArticleDraft,
    ArticleJob,
    ArticleJobProduct,
    CompetitorAnalysisReport,
    CompetitorPage,
    KeywordResearch,
    Product,
    ProductCandidate,
    QaReport,
    SerpResult,
    Source,
    WorkflowRun,
    WorkflowRunStep,
)
from app.services.local_exports import sync_article_export
from app.services.logging import create_app_log
from app.services.post_type_compat import resolve_post_type


class ArticleRecoveryError(Exception):
    pass


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _resolve_bundle_path(bundle_path: str) -> Path:
    raw = Path(bundle_path)
    candidate = raw if raw.is_absolute() else COMPLETED_ARTICLES_DIR / "articles" / raw
    overview_path = candidate / "overview.json"
    if not overview_path.exists():
        raise ArticleRecoveryError("Article export bundle not found.")
    return candidate


def _load_overview(bundle_root: Path) -> dict:
    try:
        return json.loads((bundle_root / "overview.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ArticleRecoveryError("Article export bundle is not valid JSON.") from exc


def restore_article_from_export(db: Session, bundle_path: str) -> ArticleJob:
    bundle_root = _resolve_bundle_path(bundle_path)
    payload = _load_overview(bundle_root)
    article_payload = payload.get("article") or {}
    article_id = article_payload.get("id")
    title = article_payload.get("title")
    primary_keyword = article_payload.get("primary_keyword")
    # resolve_post_type handles both new "post_type" key and legacy "article_type" key,
    # and maps old display strings (e.g. "Buying guide") to snake_case values.
    post_type = resolve_post_type(article_payload)

    if not title or not primary_keyword or not post_type:
        raise ArticleRecoveryError("Article export bundle is missing required article fields.")

    if article_id and db.get(ArticleJob, article_id):
        raise ArticleRecoveryError("An article with this export id already exists in the database.")

    existing = db.scalar(
        select(ArticleJob).where(
            ArticleJob.title == title,
            ArticleJob.primary_keyword == primary_keyword,
            ArticleJob.post_type == post_type,
        )
    )
    if existing:
        return existing

    job = ArticleJob(
        id=article_id,
        title=title,
        primary_keyword=primary_keyword,
        post_type=post_type,
        status=article_payload.get("status") or "New",
        target_audience=article_payload.get("target_audience"),
        australian_angle=article_payload.get("australian_angle"),
        notes=article_payload.get("notes"),
        review_override=bool(article_payload.get("review_override", False)),
        current_qa_score=article_payload.get("current_qa_score"),
    )
    db.add(job)
    db.flush()

    serp_id_map: dict[int, int] = {}
    for row in payload.get("serp_results") or []:
        record = SerpResult(
            article_job_id=job.id,
            keyword=row.get("keyword") or primary_keyword,
            position=row.get("position"),
            title=row.get("title"),
            url=row.get("url"),
            domain=row.get("domain"),
            snippet=row.get("snippet"),
            result_type=row.get("result_type"),
            source_payload=row.get("source_payload"),
            created_at=_parse_dt(row.get("created_at")) or datetime.utcnow(),
            updated_at=_parse_dt(row.get("updated_at")) or datetime.utcnow(),
        )
        db.add(record)
        db.flush()
        old_id = row.get("id")
        if isinstance(old_id, int):
            serp_id_map[old_id] = record.id

    for row in payload.get("keyword_research") or []:
        db.add(
            KeywordResearch(
                article_job_id=job.id,
                keyword=row.get("keyword") or primary_keyword,
                intent=row.get("intent"),
                search_volume=row.get("search_volume"),
                difficulty=row.get("difficulty"),
                cpc=row.get("cpc"),
                competition=row.get("competition"),
                source=row.get("source"),
                notes=row.get("notes"),
                source_payload=row.get("source_payload"),
                created_at=_parse_dt(row.get("created_at")) or datetime.utcnow(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.utcnow(),
            )
        )

    for row in payload.get("competitor_pages") or []:
        db.add(
            CompetitorPage(
                article_job_id=job.id,
                serp_result_id=serp_id_map.get(row.get("serp_result_id")),
                title=row.get("title"),
                url=row.get("url") or "",
                domain=row.get("domain"),
                meta_description=row.get("meta_description"),
                h1=row.get("h1"),
                h2_list=row.get("h2_list"),
                h3_list=row.get("h3_list"),
                word_count_estimate=row.get("word_count_estimate"),
                visible_text_extract=row.get("visible_text_extract"),
                detected_product_names=row.get("detected_product_names"),
                tables_count=row.get("tables_count"),
                faq_headings=row.get("faq_headings"),
                affiliate_indicators=row.get("affiliate_indicators"),
                australian_relevance_signals=row.get("australian_relevance_signals"),
                australian_relevance_score=row.get("australian_relevance_score"),
                notes=row.get("notes"),
                page_type=row.get("page_type"),
                extraction_method=row.get("extraction_method"),
                extraction_status=row.get("extraction_status"),
                error_message=row.get("error_message"),
                raw_extracted_data_json=row.get("raw_extracted_data_json"),
                created_at=_parse_dt(row.get("created_at")) or datetime.utcnow(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.utcnow(),
            )
        )

    for row in payload.get("serp_analysis_reports") or []:
        db.add(
            CompetitorAnalysisReport(
                article_job_id=job.id,
                dominant_intent=row.get("dominant_intent"),
                dominant_page_types_json=row.get("dominant_page_types_json"),
                common_headings_json=row.get("common_headings_json"),
                common_questions_json=row.get("common_questions_json"),
                repeated_products_json=row.get("repeated_products_json"),
                competitor_gaps_json=row.get("competitor_gaps_json"),
                australian_context_gaps_json=row.get("australian_context_gaps_json"),
                recommended_angle=row.get("recommended_angle"),
                original_value_recommendations_json=row.get("original_value_recommendations_json"),
                suggested_support_articles_json=row.get("suggested_support_articles_json"),
                difficulty_estimate=row.get("difficulty_estimate"),
                raw_report_json=row.get("raw_report_json"),
                created_at=_parse_dt(row.get("created_at")) or datetime.utcnow(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.utcnow(),
            )
        )

    product_id_map: dict[int, int] = {}
    for row in payload.get("article_product_links") or []:
        product_payload = row.get("product")
        product_id = None
        if isinstance(product_payload, dict):
            product = Product(
                name=product_payload.get("name") or "Not confirmed",
                brand=product_payload.get("brand"),
                category=product_payload.get("category"),
                product_url=product_payload.get("product_url"),
                personally_tested=bool(product_payload.get("personally_tested", False)),
                model_number=product_payload.get("model_number"),
                retailer_domain=product_payload.get("retailer_domain"),
                price_text=product_payload.get("price_text"),
                capacity_text=product_payload.get("capacity_text"),
                tank_size_text=product_payload.get("tank_size_text"),
                noise_level_text=product_payload.get("noise_level_text"),
                power_use_text=product_payload.get("power_use_text"),
                warranty_text=product_payload.get("warranty_text"),
                drainage_text=product_payload.get("drainage_text"),
                room_size_text=product_payload.get("room_size_text"),
                review_rating_text=product_payload.get("review_rating_text"),
                review_count_text=product_payload.get("review_count_text"),
                description_snippet=product_payload.get("description_snippet"),
                visible_specs_table=product_payload.get("visible_specs_table"),
                confidence_level=product_payload.get("confidence_level"),
                confidence_score=product_payload.get("confidence_score"),
                common_positives=product_payload.get("common_positives"),
                common_complaints=product_payload.get("common_complaints"),
                who_should_buy=product_payload.get("who_should_buy"),
                who_should_avoid=product_payload.get("who_should_avoid"),
                best_for=product_payload.get("best_for"),
                bottom_line=product_payload.get("bottom_line"),
                extraction_status=product_payload.get("extraction_status"),
                extraction_error=product_payload.get("extraction_error"),
                raw_extracted_json=product_payload.get("raw_extracted_json"),
                notes=product_payload.get("notes"),
            )
            db.add(product)
            db.flush()
            product_id = product.id
            old_product_id = product_payload.get("id")
            if isinstance(old_product_id, int):
                product_id_map[old_product_id] = product.id

        db.add(
            ArticleJobProduct(
                article_job_id=job.id,
                product_id=product_id,
                source_url=row.get("source_url") or "",
                original_source_url=row.get("original_source_url"),
                cleaned_source_url=row.get("cleaned_source_url"),
                source_type=row.get("source_type") or "other",
                extraction_status=row.get("extraction_status"),
                extraction_error=row.get("extraction_error"),
                raw_extracted_json=row.get("raw_extracted_json"),
                created_at=_parse_dt(row.get("created_at")) or datetime.utcnow(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.utcnow(),
            )
        )

    for row in payload.get("product_candidates") or []:
        db.add(
            ProductCandidate(
                article_job_id=job.id,
                product_name=row.get("product_name") or "Needs review",
                brand=row.get("brand"),
                model_number=row.get("model_number"),
                source_url=row.get("source_url"),
                source_domain=row.get("source_domain"),
                source_type=row.get("source_type") or "existing_data",
                reason_found=row.get("reason_found"),
                found_count=row.get("found_count") or 1,
                confidence_score=row.get("confidence_score"),
                suggested_best_for=row.get("suggested_best_for"),
                status=row.get("status") or "suggested",
                raw_json=row.get("raw_json"),
                created_at=_parse_dt(row.get("created_at")) or datetime.utcnow(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.utcnow(),
            )
        )

    for row in payload.get("sources") or []:
        db.add(
            Source(
                article_job_id=job.id,
                title=row.get("title") or "Recovered source",
                url=row.get("url"),
                source_type=row.get("source_type") or "reference",
                publisher=row.get("publisher"),
                trust_notes=row.get("trust_notes"),
                created_at=_parse_dt(row.get("created_at")) or datetime.utcnow(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.utcnow(),
            )
        )

    for row in payload.get("briefs") or []:
        db.add(
            ArticleBrief(
                article_job_id=job.id,
                version=row.get("version") or 1,
                brief_markdown=row.get("brief_markdown"),
                outline_json=row.get("outline_json"),
                created_at=_parse_dt(row.get("created_at")) or datetime.utcnow(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.utcnow(),
            )
        )

    for row in payload.get("drafts") or []:
        db.add(
            ArticleDraft(
                article_job_id=job.id,
                version=row.get("version") or 1,
                stage=row.get("stage") or "final",
                draft_markdown=row.get("draft_markdown"),
                seo_title=row.get("seo_title"),
                meta_description=row.get("meta_description"),
                slug=row.get("slug"),
                excerpt=row.get("excerpt"),
                model_name=row.get("model_name"),
                prompt_name=row.get("prompt_name"),
                source_payload_json=row.get("source_payload_json"),
                created_at=_parse_dt(row.get("created_at")) or datetime.utcnow(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.utcnow(),
            )
        )

    for row in payload.get("qa_reports") or []:
        db.add(
            QaReport(
                article_job_id=job.id,
                status=row.get("status") or "needs_revision",
                score=row.get("score"),
                passed_gate=bool(row.get("passed_gate", False)),
                findings_json=row.get("findings_json"),
                summary=row.get("summary"),
                model_name=row.get("model_name"),
                prompt_name=row.get("prompt_name"),
                created_at=_parse_dt(row.get("created_at")) or datetime.utcnow(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.utcnow(),
            )
        )

    for row in payload.get("workflow_runs") or []:
        run = WorkflowRun(
            article_job_id=job.id,
            workflow_mode=row.get("workflow_mode") or "full_draft",
            research_mode=row.get("research_mode") or "fresh",
            status=row.get("status") or "failed",
            current_step=row.get("current_step"),
            summary_message=row.get("summary_message"),
            created_at=_parse_dt(row.get("created_at")) or datetime.utcnow(),
            updated_at=_parse_dt(row.get("updated_at")) or datetime.utcnow(),
        )
        db.add(run)
        db.flush()
        for step in row.get("steps") or []:
            db.add(
                WorkflowRunStep(
                    workflow_run_id=run.id,
                    step_key=step.get("step_key") or "unknown",
                    step_label=step.get("step_label") or "Unknown step",
                    status=step.get("status") or "pending",
                    message=step.get("message"),
                    created_at=run.created_at,
                    updated_at=run.updated_at,
                )
            )

    for row in payload.get("app_logs") or []:
        if row.get("event_type") == "article_job.recovered":
            continue
        db.add(
            AppLog(
                level=row.get("level") or "INFO",
                event_type=row.get("event_type") or "article.recovered.log",
                message=row.get("message") or "Recovered log entry.",
                article_job_id=job.id,
                metadata_json=row.get("metadata_json"),
                created_at=_parse_dt(row.get("created_at")) or datetime.utcnow(),
                updated_at=_parse_dt(row.get("updated_at")) or datetime.utcnow(),
            )
        )

    db.commit()
    db.refresh(job)
    create_app_log(
        db,
        event_type="article_job.recovered",
        message=f"Article restored from local export bundle '{bundle_root.name}'.",
        article_job_id=job.id,
        metadata_json={"bundle_path": str(bundle_root.resolve())},
    )
    sync_article_export(db, job, reason="article_recovered")
    return job
