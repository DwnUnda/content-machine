import json
import os
import subprocess
from pathlib import Path
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.entities import (
    ArticleBrief,
    ArticleDraft,
    ArticleJob,
    ArticleJobStatus,
    PostType,
    CompetitorAnalysisReport,
    CompetitorPage,
    CostLog,
    KeywordResearch,
    QaReport,
    SerpResult,
    AppLog,
    WorkflowRun,
    WorkflowRunStep,
    WordPressExport,
)
from app.services.article_drafting import generate_draft as generate_ai_draft
from app.services.article_drafting import run_fix_pass as run_ai_fix_pass
from app.services.article_drafting import run_human_edit as run_ai_human_edit
from app.services.article_drafting import run_qa as run_ai_qa
from app.services.article_drafting import classify_serp_intent as classify_ai_serp_intent
from app.services.article_drafting import ArticleDraftingError
from app.services.product_candidates import (
    ProductCandidateError,
    approve_product_candidate,
    convert_product_candidate,
    discover_product_candidates,
    ignore_product_candidate,
)
from app.services.reddit_feedback import RedditFeedbackError, research_reddit_feedback
from app.core.config import get_settings
from app.services.competitor_extraction import extract_competitors_for_job
from app.services.dataforseo import DataForSEOClient, DataForSEOError, parse_keyword_ideas, parse_serp_items
from app.services.logging import create_app_log
from app.services.local_exports import sync_article_export
from app.services.research_brief import build_research_brief_payload, render_research_brief_markdown
from app.services.serp_analysis import analyse_serp_for_job
from app.services.html_validation import serialise_html_validation, validate_latest_article_html


PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
NOT_CONFIRMED = "Not confirmed"
# Per-post-type minimum number of draft-ready product cards required before
# the draft step is permitted.  0 means products are not required.
POST_TYPE_MIN_PRODUCTS: dict[str, int] = {
    PostType.INFORMATIONAL_BLOG.value: 0,
    PostType.MONEY_POST.value: 3,
    PostType.SINGLE_PRODUCT_REVIEW.value: 1,
    PostType.PRODUCT_COMPARISON.value: 2,
    PostType.BEST_X_FOR_Y.value: 3,
}
MAX_PRODUCT_CARDS = 5


def get_min_products_for_post_type(post_type: str) -> int:
    """Return the minimum draft-ready product cards required for *post_type*."""
    return POST_TYPE_MIN_PRODUCTS.get(post_type, 0)


def is_product_gated_post_type(post_type: str) -> bool:
    """Return True if the post type requires at least one product card."""
    return get_min_products_for_post_type(post_type) > 0
WORKFLOW_STEP_SPECS = [
    ("serp_research", "SERP research"),
    ("keyword_research", "Keyword research"),
    ("competitor_extraction", "Competitor extraction"),
    ("serp_analysis", "SERP analysis"),
    ("serp_intent", "SERP intent classification"),
    ("research_brief", "Research brief generation"),
    ("product_research", "Product research"),
    ("reddit_feedback", "Reddit feedback research"),
    ("draft_generation", "Draft generation"),
    ("human_edit", "Australian human polish"),
    ("qa", "QA"),
    ("fix_pass", "Fix pass"),
    ("qa_recheck", "QA recheck"),
]
PAID_WORKFLOW_STEPS = {"serp_research", "keyword_research", "product_research", "reddit_feedback"}
STEP_INDEX = {step_key: index for index, (step_key, _) in enumerate(WORKFLOW_STEP_SPECS)}
DOWNSTREAM_INVALIDATION = {
    "serp_research": {"competitor_extraction", "serp_analysis", "serp_intent", "research_brief", "draft_generation", "human_edit", "qa", "fix_pass", "qa_recheck"},
    "keyword_research": {"serp_analysis", "serp_intent", "research_brief", "draft_generation", "human_edit", "qa", "fix_pass", "qa_recheck"},
    "competitor_extraction": {"serp_analysis", "serp_intent", "research_brief", "draft_generation", "human_edit", "qa", "fix_pass", "qa_recheck"},
    "serp_analysis": {"serp_intent", "research_brief", "draft_generation", "human_edit", "qa", "fix_pass", "qa_recheck"},
    "serp_intent": {"research_brief", "draft_generation", "human_edit", "qa", "fix_pass", "qa_recheck"},
    "research_brief": {"draft_generation", "human_edit", "qa", "fix_pass", "qa_recheck"},
    # Product research is independent of the research/brief chain, so it is not invalidated
    # by upstream reruns; but changing product cards must re-run drafting and everything after.
    "product_research": {"reddit_feedback", "draft_generation", "human_edit", "qa", "fix_pass", "qa_recheck"},
    "reddit_feedback": {"draft_generation", "human_edit", "qa", "fix_pass", "qa_recheck"},
    # Order: draft -> human polish -> qa.
    "draft_generation": {"human_edit", "qa", "fix_pass", "qa_recheck"},
    "human_edit": {"qa", "fix_pass", "qa_recheck"},
    "qa": set(),
    "fix_pass": {"qa_recheck"},
    "qa_recheck": set(),
}


def _prompt_path(name: str) -> str:
    return str(PROMPTS_DIR / name)


def _latest_row(db: Session, model: type, article_job_id: int):
    return db.scalar(
        select(model)
        .where(model.article_job_id == article_job_id)
        .order_by(desc(model.updated_at), desc(model.created_at))
    )


def _latest_step_status_map(db: Session, article_job_id: int) -> dict[str, tuple[str, str | None]]:
    latest_run = db.scalar(
        select(WorkflowRun)
        .where(WorkflowRun.article_job_id == article_job_id)
        .order_by(desc(WorkflowRun.created_at))
    )
    if not latest_run:
        return {}
    steps = list(
        db.scalars(
            select(WorkflowRunStep)
            .where(WorkflowRunStep.workflow_run_id == latest_run.id)
        ).all()
    )
    return {step.step_key: (step.status, step.message) for step in steps}


def _latest_completed_log_exists(db: Session, article_job_id: int, event_type: str) -> bool:
    return bool(
        db.scalar(
            select(AppLog.id)
            .where(AppLog.article_job_id == article_job_id, AppLog.event_type == event_type)
            .limit(1)
        )
    )


def _latest_app_log(db: Session, article_job_id: int, event_type: str) -> AppLog | None:
    return db.scalar(
        select(AppLog)
        .where(AppLog.article_job_id == article_job_id, AppLog.event_type == event_type)
        .order_by(desc(AppLog.created_at))
    )


def _max_timestamp(*values: datetime | None) -> datetime | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _latest_qa_findings(db: Session, article_job_id: int) -> dict:
    report = db.scalar(
        select(QaReport)
        .where(QaReport.article_job_id == article_job_id)
        .order_by(desc(QaReport.created_at))
    )
    findings = getattr(report, "findings_json", None)
    return findings if isinstance(findings, dict) else {}


def _qa_findings_actionable(findings: dict) -> bool:
    """True if QA produced concrete, fixable issues worth a fix pass.

    A fix pass is only worth running when QA flagged failed checks, gave fix
    instructions, or the draft is below the minimum word count. Vague or minor
    non-actionable comments do not justify a full fix-pass rewrite.
    """
    if not isinstance(findings, dict):
        return False
    if findings.get("failed_checks"):
        return True
    if findings.get("fix_instructions"):
        return True
    if findings.get("minimum_word_count_passed") is False:
        return True
    return False


def _summarise_run_usage(db: Session, article_job_id: int, since: datetime | None) -> dict:
    """Aggregate safe AI usage logged during this run (no secrets)."""
    totals = {"ai_calls": 0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}
    query = select(AppLog).where(AppLog.article_job_id == article_job_id)
    if since is not None:
        query = query.where(AppLog.created_at >= since)
    rows = list(db.scalars(query).all())

    def _add(usage: object) -> None:
        if not isinstance(usage, dict):
            return
        if usage.get("input_tokens") is None and usage.get("output_tokens") is None:
            return
        totals["ai_calls"] += 1
        for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
            value = usage.get(key)
            if isinstance(value, (int, float)):
                totals[key] += value

    for row in rows:
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        _add(metadata)
        _add(metadata.get("qa_usage"))
        _add(metadata.get("seo_usage"))
    return totals


def _timestamp_of(row) -> datetime | None:
    if row is None:
        return None
    return getattr(row, "updated_at", None) or getattr(row, "created_at", None)


def _is_stale(current_ts: datetime | None, dependency_ts: datetime | None, *, tolerance_seconds: float = 1.0) -> bool:
    if not current_ts or not dependency_ts:
        return False
    return (dependency_ts - current_ts).total_seconds() > tolerance_seconds


def _workflow_step_state(detail: str | None, *, status: str, paid_step: bool = False) -> dict:
    return {
        "status": status,
        "detail": detail,
        "paid_step": paid_step,
    }


def _coerce_summary_text(value: object, fallback: str) -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return fallback
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return text
            if isinstance(parsed, dict):
                parts: list[str] = []
                score = parsed.get("score")
                if score is not None:
                    parts.append(f"QA score {score}.")
                summary = parsed.get("summary")
                if isinstance(summary, str) and summary.strip():
                    parts.append(summary.strip())
                failed_checks = parsed.get("failed_checks")
                if isinstance(failed_checks, list) and failed_checks:
                    first_check = failed_checks[0]
                    if isinstance(first_check, dict):
                        issue = first_check.get("issue") or first_check.get("check")
                        if issue:
                            parts.append(str(issue))
                    else:
                        parts.append(str(first_check))
                warnings = parsed.get("warnings")
                if isinstance(warnings, list) and warnings:
                    first_warning = warnings[0]
                    if isinstance(first_warning, str) and first_warning.strip():
                        parts.append(first_warning.strip())
                combined = " ".join(parts).strip()
                return combined or text
        return text
    if isinstance(value, dict):
        parts: list[str] = []
        score = value.get("score")
        if score is not None:
            parts.append(f"QA score {score}.")
        summary = value.get("summary")
        if isinstance(summary, str) and summary.strip():
            parts.append(summary.strip())
        failed_checks = value.get("failed_checks")
        if isinstance(failed_checks, list) and failed_checks:
            first_check = failed_checks[0]
            if isinstance(first_check, dict):
                issue = first_check.get("issue") or first_check.get("check")
                if issue:
                    parts.append(str(issue))
            else:
                parts.append(str(first_check))
        combined = " ".join(parts).strip()
        return combined or fallback
    return str(value).strip() or fallback


def _publish_check(key: str, label: str, passed: bool, detail: str) -> dict:
    return {"key": key, "label": label, "passed": passed, "detail": detail}


def _latest_html_file(job: ArticleJob, latest_draft: ArticleDraft | None) -> Path | None:
    if not job.local_export_path:
        return None
    root = Path(job.local_export_path)
    if not root.exists():
        return None
    candidates: list[Path] = []
    if latest_draft and latest_draft.slug:
        candidates.append(root / f"{latest_draft.slug}.html")
    candidates.extend(sorted(root.glob("*.html"), key=lambda path: path.stat().st_mtime, reverse=True))
    return next((path for path in candidates if path.exists()), None)


def build_publish_readiness(db: Session, job: ArticleJob) -> dict:
    latest_draft = _latest_row(db, ArticleDraft, job.id)
    latest_qa = _latest_row(db, QaReport, job.id)
    min_products = get_min_products_for_post_type(job.post_type)
    draft_ready_products = sum(
        1 for link in getattr(job, "article_product_links", []) if link and getattr(link, "draft_ready", False)
    )
    html_file = _latest_html_file(job, latest_draft)

    checks = [
        _publish_check(
            "final_draft",
            "Final draft exists",
            bool(latest_draft and latest_draft.stage == "final" and latest_draft.draft_markdown),
            f"Latest draft stage is {latest_draft.stage}." if latest_draft else "No draft exists yet.",
        ),
        _publish_check(
            "product_cards",
            "Product cards ready",
            min_products == 0 or draft_ready_products >= min_products,
            (
                "Product cards are not required for this post type."
                if min_products == 0
                else f"{draft_ready_products}/{min_products} required product cards are draft-ready."
            ),
        ),
        _publish_check(
            "qa_passed",
            "QA passed",
            bool(latest_qa and latest_qa.passed_gate),
            f"Latest QA score: {latest_qa.score}." if latest_qa else "QA has not run on the latest draft.",
        ),
        _publish_check(
            "html_generated",
            "HTML file generated",
            bool(html_file),
            str(html_file) if html_file else "No local HTML file found yet.",
        ),
    ]

    html_validation_payload = None
    try:
        html_validation = validate_latest_article_html(db, job, wordpress_blocks=True)
        html_validation_payload = serialise_html_validation(html_validation)
        wordpress_block_passed = next(
            (check.passed for check in html_validation.checks if check.key == "wordpress_block"),
            False,
        )
        checks.append(_publish_check("html_structure", "HTML structure passed", html_validation.passed, html_validation.summary))
        checks.append(
            _publish_check(
                "wordpress_html_block",
                "WordPress HTML block wrapper",
                bool(wordpress_block_passed),
                "Rendered WordPress upload HTML is wrapped in a Gutenberg HTML block.",
            )
        )
    except Exception as exc:  # noqa: BLE001
        html_validation_payload = {"passed": False, "summary": f"HTML validation failed: {exc}", "checks": []}
        checks.append(_publish_check("html_structure", "HTML structure passed", False, f"HTML validation failed: {exc}"))
        checks.append(_publish_check("wordpress_html_block", "WordPress HTML block wrapper", False, "Could not validate WordPress HTML block wrapper."))

    ready = all(check["passed"] for check in checks)
    failed_count = len([check for check in checks if not check["passed"]])
    return {
        "ready": ready,
        "summary": "Ready for WordPress draft upload." if ready else f"Not publish-ready yet: {failed_count} check(s) need attention.",
        "checks": checks,
        "html_validation": html_validation_payload,
    }


def get_workflow_state(db: Session, job: ArticleJob) -> dict:
    latest_step_status = _latest_step_status_map(db, job.id)
    latest_serp = _latest_row(db, SerpResult, job.id)
    latest_keyword = _latest_row(db, KeywordResearch, job.id)
    latest_competitor = _latest_row(db, CompetitorPage, job.id)
    latest_analysis = _latest_row(db, CompetitorAnalysisReport, job.id)
    latest_brief = _latest_row(db, ArticleBrief, job.id)
    latest_draft = _latest_row(db, ArticleDraft, job.id)
    latest_qa = _latest_row(db, QaReport, job.id)
    latest_reddit_feedback = _latest_app_log(db, job.id, "workflow.reddit_feedback.completed")

    draft_rows = list(
        db.scalars(
            select(ArticleDraft)
            .where(ArticleDraft.article_job_id == job.id)
            .order_by(desc(ArticleDraft.updated_at), desc(ArticleDraft.created_at))
        ).all()
    )
    latest_first_draft = next((row for row in draft_rows if row.stage == "first_draft"), None)
    latest_human_edit = next((row for row in draft_rows if row.stage == "human_edit"), None)
    latest_fix_pass = next((row for row in draft_rows if row.stage == "fix_pass"), None)

    qa_rows = list(
        db.scalars(
            select(QaReport)
            .where(QaReport.article_job_id == job.id)
            .order_by(desc(QaReport.updated_at), desc(QaReport.created_at))
        ).all()
    )
    latest_initial_qa = next(
        (
            row for row in qa_rows
            if isinstance(row.findings_json, dict) and row.findings_json.get("stage") == "initial"
        ),
        qa_rows[0] if qa_rows else None,
    )
    latest_recheck_qa = next(
        (
            row for row in qa_rows
            if isinstance(row.findings_json, dict) and row.findings_json.get("stage") == "recheck"
        ),
        None,
    )

    linked_products = [link for link in getattr(job, "article_product_links", []) if link]
    latest_product_update = _max_timestamp(
        *[
            _max_timestamp(_timestamp_of(link), _timestamp_of(getattr(link, "product", None)))
            for link in linked_products
        ]
    )

    serp_ts = _timestamp_of(latest_serp)
    keyword_ts = _timestamp_of(latest_keyword)
    competitor_ts = _timestamp_of(latest_competitor)
    analysis_ts = _timestamp_of(latest_analysis)
    brief_ts = _timestamp_of(latest_brief)
    reddit_feedback_ts = _timestamp_of(latest_reddit_feedback)
    first_draft_ts = _timestamp_of(latest_first_draft)
    human_edit_ts = _timestamp_of(latest_human_edit)
    fix_pass_ts = _timestamp_of(latest_fix_pass)
    draft_ts = _timestamp_of(latest_draft)
    initial_qa_ts = _timestamp_of(latest_initial_qa)
    recheck_qa_ts = _timestamp_of(latest_recheck_qa)

    states: dict[str, dict] = {}

    serp_complete = bool(latest_serp and latest_serp.keyword == job.primary_keyword)
    if serp_complete:
        states["serp_research"] = _workflow_step_state(
            f"Stored SERP results available for '{job.primary_keyword}'.",
            status="complete",
            paid_step=True,
        )
    else:
        prior_status = latest_step_status.get("serp_research", ("missing", None))
        states["serp_research"] = _workflow_step_state(
            prior_status[1] or "SERP research has not been completed for the current keyword.",
            status="failed" if prior_status[0] == "failed" else "missing",
            paid_step=True,
        )

    keyword_complete = bool(latest_keyword) or _latest_completed_log_exists(
        db, job.id, "workflow.keyword_research.completed"
    )
    if keyword_complete:
        keyword_detail = (
            "Stored keyword research available."
            if latest_keyword
            else "Keyword research previously completed with no saved keyword rows."
        )
        states["keyword_research"] = _workflow_step_state(keyword_detail, status="complete", paid_step=True)
    else:
        prior_status = latest_step_status.get("keyword_research", ("missing", None))
        states["keyword_research"] = _workflow_step_state(
            prior_status[1] or "Keyword research has not been completed for the current keyword.",
            status="failed" if prior_status[0] == "failed" else "missing",
            paid_step=True,
        )

    competitor_dependency_ts = serp_ts
    if competitor_ts:
        competitor_status = "stale" if _is_stale(competitor_ts, competitor_dependency_ts) else "complete"
        competitor_detail = (
            "Competitor extraction is older than the latest SERP research."
            if competitor_status == "stale"
            else "Stored competitor extraction available."
        )
    else:
        prior_status = latest_step_status.get("competitor_extraction", ("missing", None))
        competitor_status = "failed" if prior_status[0] == "failed" else "missing"
        competitor_detail = prior_status[1] or "Competitor pages have not been extracted yet."
    states["competitor_extraction"] = _workflow_step_state(competitor_detail, status=competitor_status)

    analysis_dependency_ts = _max_timestamp(serp_ts, keyword_ts, competitor_ts)
    if latest_analysis:
        analysis_status = "stale" if _is_stale(analysis_ts, analysis_dependency_ts) else "complete"
        analysis_detail = (
            "SERP analysis is older than the current research inputs."
            if analysis_status == "stale"
            else "Stored SERP analysis available."
        )
    else:
        prior_status = latest_step_status.get("serp_analysis", ("missing", None))
        analysis_status = "failed" if prior_status[0] == "failed" else "missing"
        analysis_detail = prior_status[1] or "SERP analysis has not been generated yet."
    states["serp_analysis"] = _workflow_step_state(analysis_detail, status=analysis_status)

    serp_intent_present = bool(latest_brief and latest_brief.serp_intent_json)
    serp_intent_dependency_ts = _max_timestamp(analysis_ts, competitor_ts, keyword_ts, serp_ts)
    if serp_intent_present:
        intent_status = "stale" if _is_stale(brief_ts, serp_intent_dependency_ts) else "complete"
        intent_detail = (
            "SERP intent classification is older than the current research inputs."
            if intent_status == "stale"
            else "Stored SERP intent classification available."
        )
    else:
        prior_status = latest_step_status.get("serp_intent", ("missing", None))
        intent_status = "failed" if prior_status[0] == "failed" else "missing"
        intent_detail = prior_status[1] or "SERP intent has not been classified yet."
    states["serp_intent"] = _workflow_step_state(intent_detail, status=intent_status)

    brief_dependency_ts = _max_timestamp(analysis_ts, competitor_ts, keyword_ts, serp_ts)
    if latest_brief:
        brief_status = "stale" if _is_stale(brief_ts, brief_dependency_ts) else "complete"
        brief_detail = (
            "Research brief is older than the latest analysis or research."
            if brief_status == "stale"
            else "Stored research brief available."
        )
    else:
        prior_status = latest_step_status.get("research_brief", ("missing", None))
        brief_status = "failed" if prior_status[0] == "failed" else "missing"
        brief_detail = prior_status[1] or "Research brief has not been generated yet."
    states["research_brief"] = _workflow_step_state(brief_detail, status=brief_status)

    min_products = get_min_products_for_post_type(job.post_type)
    if min_products == 0:
        product_research_status = "not_required"
        product_research_detail = "Product cards are not required for this post type."
    else:
        draft_ready_count = sum(
            1 for link in getattr(job, "article_product_links", []) if link and getattr(link, "draft_ready", False)
        )
        if draft_ready_count >= min_products:
            product_research_status = "complete"
            product_research_detail = f"{draft_ready_count} draft-ready product cards available."
        else:
            prior_status = latest_step_status.get("product_research", ("missing", None))
            product_research_status = "failed" if prior_status[0] == "failed" else "missing"
            product_research_detail = (
                prior_status[1]
                or f"Needs {min_products} draft-ready product card{'s' if min_products != 1 else ''}; web-search research and discovery will run automatically."
            )
    states["product_research"] = _workflow_step_state(
        product_research_detail,
        status=product_research_status,
        paid_step=is_product_gated_post_type(job.post_type) and bool(get_settings().openai_api_key),
    )

    reddit_dependency_ts = latest_product_update or brief_ts
    if not get_settings().openai_api_key:
        reddit_status = "not_required"
        reddit_detail = "Reddit feedback research skipped because OpenAI web search is not configured."
    elif latest_reddit_feedback:
        reddit_status = "stale" if _is_stale(reddit_feedback_ts, reddit_dependency_ts) else "complete"
        metadata = latest_reddit_feedback.metadata_json if isinstance(latest_reddit_feedback.metadata_json, dict) else {}
        qualified_count = len(metadata.get("qualified_patterns") or [])
        rejected_count = len(metadata.get("rejected_patterns") or [])
        reddit_detail = (
            "Reddit feedback is older than the latest product research."
            if reddit_status == "stale"
            else f"Stored Reddit feedback available: {qualified_count} qualified pattern(s), {rejected_count} rejected."
        )
    else:
        prior_status = latest_step_status.get("reddit_feedback", ("missing", None))
        reddit_status = "failed" if prior_status[0] == "failed" else "missing"
        reddit_detail = prior_status[1] or "Reddit feedback has not been researched yet."
    states["reddit_feedback"] = _workflow_step_state(reddit_detail, status=reddit_status, paid_step=bool(get_settings().openai_api_key))

    draft_dependency_ts = _max_timestamp(brief_ts, latest_product_update, reddit_feedback_ts)
    if latest_first_draft or latest_human_edit or latest_fix_pass or (latest_draft and latest_draft.stage == "final"):
        effective_draft_ts = _max_timestamp(first_draft_ts, human_edit_ts, fix_pass_ts, draft_ts)
        draft_status = "stale" if _is_stale(effective_draft_ts, draft_dependency_ts) else "complete"
        draft_detail = (
            "Draft is older than the latest brief or product card updates."
            if draft_status == "stale"
            else "Stored draft available."
        )
    else:
        readiness = get_drafting_readiness(db, job)
        prior_status = latest_step_status.get("draft_generation", ("missing", None))
        if not readiness["can_generate_draft"]:
            draft_status = "blocked"
            draft_detail = readiness["issues"][0]
        else:
            draft_status = "failed" if prior_status[0] == "failed" else "missing"
            draft_detail = prior_status[1] or "Draft generation has not been completed yet."
    states["draft_generation"] = _workflow_step_state(draft_detail, status=draft_status)

    human_edit_dependency_ts = first_draft_ts
    if latest_human_edit or latest_fix_pass or (latest_draft and latest_draft.stage == "final"):
        effective_human_ts = _max_timestamp(human_edit_ts, fix_pass_ts, draft_ts)
        human_status = "stale" if _is_stale(effective_human_ts, human_edit_dependency_ts) else "complete"
        human_detail = (
            "Human polish is older than the latest draft."
            if human_status == "stale"
            else "Stored human-polished draft available."
        )
    else:
        prior_status = latest_step_status.get("human_edit", ("missing", None))
        human_status = "failed" if prior_status[0] == "failed" else "missing"
        human_detail = prior_status[1] or "Australian human polish has not been completed yet."
    states["human_edit"] = _workflow_step_state(human_detail, status=human_status)

    qa_dependency_ts = _max_timestamp(human_edit_ts, fix_pass_ts, draft_ts)
    if latest_qa:
        current_qa_ts = recheck_qa_ts or initial_qa_ts
        if _is_stale(current_qa_ts, qa_dependency_ts):
            qa_status = "stale"
            qa_detail = "QA is older than the latest draft revision."
        elif latest_qa.passed_gate:
            qa_status = "complete"
            qa_detail = "Latest draft passed QA."
        else:
            qa_status = "failed"
            qa_detail = _coerce_summary_text(latest_qa.summary, "Latest draft failed QA and needs revision.")
    else:
        prior_status = latest_step_status.get("qa", ("missing", None))
        qa_status = "failed" if prior_status[0] == "failed" else "missing"
        qa_detail = prior_status[1] or "QA has not been run yet."
    states["qa"] = _workflow_step_state(qa_detail, status=qa_status)

    if latest_initial_qa and not latest_initial_qa.passed_gate and (not fix_pass_ts or (initial_qa_ts and fix_pass_ts and fix_pass_ts < initial_qa_ts)):
        fix_status = "missing"
        fix_detail = "QA failed. A fix pass is the next cheapest recovery step."
    elif latest_fix_pass:
        if latest_initial_qa and initial_qa_ts and fix_pass_ts and fix_pass_ts < initial_qa_ts:
            fix_status = "stale"
            fix_detail = "Fix pass is older than the latest failed QA report."
        else:
            fix_status = "complete"
            fix_detail = "Fix pass draft is available."
    else:
        fix_status = "not_required"
        fix_detail = "Fix pass is not required unless QA fails."
    states["fix_pass"] = _workflow_step_state(fix_detail, status=fix_status)

    if latest_fix_pass:
        if latest_recheck_qa and recheck_qa_ts and fix_pass_ts and recheck_qa_ts >= fix_pass_ts:
            if latest_recheck_qa.passed_gate:
                recheck_status = "complete"
                recheck_detail = "QA recheck passed after the fix pass."
            else:
                recheck_status = "failed"
                recheck_detail = _coerce_summary_text(latest_recheck_qa.summary, "QA recheck failed after the fix pass.")
        else:
            recheck_status = "missing"
            recheck_detail = "Run QA again to verify the fix pass."
    else:
        recheck_status = "not_required"
        recheck_detail = "QA recheck is only needed after a fix pass."
    states["qa_recheck"] = _workflow_step_state(recheck_detail, status=recheck_status)

    has_existing_work = any(state["status"] in {"complete", "stale", "failed", "blocked"} for state in states.values())
    recommended_mode = "resume_current" if has_existing_work else "fresh"

    next_step_key = None
    next_action = "Review draft"
    summary_message = "The article is ready to continue from its current state."
    if states["qa"]["status"] == "failed" and states["fix_pass"]["status"] in {"missing", "stale"}:
        next_step_key = "fix_pass"
    else:
        for step_key, _label in WORKFLOW_STEP_SPECS:
            status = states[step_key]["status"]
            if status in {"missing", "stale", "failed", "blocked"}:
                next_step_key = step_key
                break

    if next_step_key == "fix_pass":
        next_action = "Run fix pass"
        summary_message = states["fix_pass"]["detail"] or "QA failed. Run a fix pass next."
    elif next_step_key == "qa_recheck":
        next_action = "Run QA recheck"
        summary_message = states["qa_recheck"]["detail"] or "Run QA again to verify the fix pass."
    elif next_step_key == "qa":
        next_action = "Run QA"
        summary_message = states["qa"]["detail"] or "Run QA on the latest draft."
    elif next_step_key == "human_edit":
        next_action = "Run human polish"
        summary_message = states["human_edit"]["detail"] or "Human polish is the next required step."
    elif next_step_key == "draft_generation":
        next_action = "Generate draft"
        summary_message = states["draft_generation"]["detail"] or "Draft generation is the next required step."
    elif next_step_key == "product_research":
        next_action = "Run product research"
        summary_message = states["product_research"]["detail"] or "Find and research product cards next."
    elif next_step_key == "research_brief":
        next_action = "Generate research brief"
        summary_message = states["research_brief"]["detail"] or "Research brief generation is the next required step."
    elif next_step_key == "serp_intent":
        next_action = "Classify SERP intent"
        summary_message = states["serp_intent"]["detail"] or "SERP intent classification is the next required step."
    elif next_step_key == "serp_analysis":
        next_action = "Analyse SERP"
        summary_message = states["serp_analysis"]["detail"] or "SERP analysis is the next required step."
    elif next_step_key == "competitor_extraction":
        next_action = "Extract competitors"
        summary_message = states["competitor_extraction"]["detail"] or "Competitor extraction is the next required step."
    elif next_step_key == "keyword_research":
        next_action = "Run keyword research"
        summary_message = states["keyword_research"]["detail"] or "Keyword research is the next required step."
    elif next_step_key == "serp_research":
        next_action = "Run SERP research"
        summary_message = states["serp_research"]["detail"] or "SERP research is the next required step."
    elif latest_qa and latest_qa.passed_gate:
        next_action = "Review final draft"
        summary_message = "Research, drafting, and QA are already complete for the latest draft."

    estimated_paid_calls = 0
    for step_key in PAID_WORKFLOW_STEPS:
        status = states[step_key]["status"]
        if recommended_mode == "fresh" or status in {"missing", "stale", "failed"}:
            estimated_paid_calls += 1

    return {
        "article_job_id": job.id,
        "recommended_research_mode": recommended_mode,
        "next_recommended_action": next_action,
        "next_step_key": next_step_key,
        "summary_message": summary_message,
        "estimated_paid_calls": estimated_paid_calls,
        "has_existing_work": has_existing_work,
        "steps": [
            {
                "step_key": step_key,
                "step_label": label,
                **states[step_key],
            }
            for step_key, label in WORKFLOW_STEP_SPECS
        ],
        "publish_readiness": build_publish_readiness(db, job),
    }


def _save_job(db: Session, job: ArticleJob, status: str) -> ArticleJob:
    job.status = status
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _save_workflow_run(db: Session, run: WorkflowRun, *, status: str, current_step: str | None, summary_message: str | None = None) -> WorkflowRun:
    run.status = status
    run.current_step = current_step
    if summary_message is not None:
        run.summary_message = summary_message
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _create_workflow_run(db: Session, *, article_job_id: int, workflow_mode: str, research_mode: str) -> WorkflowRun:
    run = WorkflowRun(
        article_job_id=article_job_id,
        workflow_mode=workflow_mode,
        research_mode=research_mode,
        status="running",
        current_step=None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _create_workflow_step(db: Session, *, workflow_run_id: int, step_key: str, step_label: str) -> WorkflowRunStep:
    step = WorkflowRunStep(
        workflow_run_id=workflow_run_id,
        step_key=step_key,
        step_label=step_label,
        status="pending",
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


def _sync_local_export(db: Session, job: ArticleJob, reason: str) -> None:
    try:
        sync_article_export(db, job, reason=reason)
    except Exception as exc:  # noqa: BLE001
        create_app_log(
            db,
            event_type="workflow.local_export.failed",
            message=f"Local export sync failed: {exc}",
            article_job_id=job.id,
            level="WARNING",
            metadata_json={"reason": reason},
        )


def _update_workflow_step(db: Session, step: WorkflowRunStep, *, status: str, message: str) -> WorkflowRunStep:
    step.status = status
    step.message = message
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


def _create_cost_log(
    db: Session,
    *,
    article_job_id: int,
    action: str,
    endpoint: str,
    cost: float | None,
    request_count: int = 1,
) -> None:
    cost_log = CostLog(
        provider="DataForSEO",
        action=action,
        cost_amount=cost,
        currency="USD" if cost is not None else None,
        related_entity_type="article_job",
        related_entity_id=article_job_id,
        notes=f"endpoint={endpoint}; request_count={request_count}",
    )
    db.add(cost_log)
    db.commit()


def _has_record(db: Session, model: type, article_job_id: int) -> bool:
    return bool(db.scalar(select(model.id).where(model.article_job_id == article_job_id).limit(1)))


def _is_missing_value(value: str | None) -> bool:
    return value is None or not str(value).strip() or str(value).strip() == NOT_CONFIRMED


def _linked_product_missing_fields(link) -> list[str]:
    return list(getattr(link, "draft_blocking_missing_fields", []))


def get_drafting_readiness(db: Session, job: ArticleJob) -> dict:
    linked_products = [link for link in getattr(job, "article_product_links", []) if link]
    draft_ready_links = [link for link in linked_products if getattr(link, "draft_ready", False)]
    min_products_required = get_min_products_for_post_type(job.post_type)
    needs_product_cards = min_products_required > 0
    issues: list[str] = []

    # Per-card breakdown so the UI can explain why a money page is or is not ready.
    per_product: list[dict] = []
    extraction_failed = 0
    needs_review = 0
    for link in linked_products:
        status = getattr(link, "extraction_status", None) or "pending"
        is_ready = getattr(link, "draft_ready", False)
        if status == "extraction_failed":
            extraction_failed += 1
        if getattr(link, "needs_review", False) and not is_ready:
            needs_review += 1
        per_product.append(
            {
                "id": link.id,
                "product_id": link.product_id,
                "name": (link.product.name if link.product else None) or getattr(link, "inferred_name", None),
                "status": status,
                "draft_ready": is_ready,
                "needs_review": getattr(link, "needs_review", False),
                "extraction_failure_reason": getattr(link, "extraction_failure_reason", None),
                "reason_not_draft_ready": None
                if is_ready
                else "; ".join(_linked_product_missing_fields(link))
                or (getattr(link, "extraction_failure_reason", None) or "Needs review before it can count."),
            }
        )

    if not _has_record(db, ArticleBrief, job.id):
        issues.append("Research brief is required before drafting.")
    if not _has_record(db, CompetitorAnalysisReport, job.id):
        issues.append("SERP analysis is required before drafting.")
    if needs_product_cards and len(draft_ready_links) < min_products_required:
        reason_bits = []
        if extraction_failed:
            reason_bits.append(f"{extraction_failed} need product research because direct extraction failed")
        if needs_review:
            reason_bits.append(f"{needs_review} need review before they count")
        tail = (" " + "; ".join(reason_bits) + ".") if reason_bits else ""
        issues.append(
            f"{len(linked_products)} product URL{'s' if len(linked_products) != 1 else ''} found. "
            f"{len(draft_ready_links)} draft-ready card{'s' if len(draft_ready_links) != 1 else ''}. "
            f"This post needs at least {min_products_required} draft-ready product card{'s' if min_products_required != 1 else ''} before a proper draft "
            f"can be generated.{tail}"
        )

    return {
        "post_type": job.post_type,
        "needs_product_cards": needs_product_cards,
        "linked_products": len(linked_products),
        "urls_added": len(linked_products),
        "draft_ready_products": len(draft_ready_links),
        "extraction_failed": extraction_failed,
        "needs_review": needs_review,
        "per_product": per_product,
        "can_generate_draft": not issues,
        "issues": issues,
    }


def _draft_ready_count(job: ArticleJob) -> int:
    return sum(1 for link in getattr(job, "article_product_links", []) if link and getattr(link, "draft_ready", False))


def run_product_research(db: Session, job: ArticleJob) -> dict:
    """Automatic product step for money pages: research+verify any not-yet-ready linked
    products, and if still below the floor, discover more via web search and research them.
    Auto-approval happens inside research_product_via_websearch. Never raises on partial
    failure — the draft-generation gate is the safety net when too few cards qualify."""
    if not is_product_gated_post_type(job.post_type):
        return {"message": "Product research not required for this post type."}
    if not get_settings().openai_api_key:
        return {"message": "Product research skipped: OpenAI web search is not configured."}

    from app.services.product_research import (
        ProductResearchError,
        discover_products_via_websearch,
        research_product_via_websearch,
    )

    def _log_card_failure(link_id: int | None, exc: Exception) -> None:
        create_app_log(
            db,
            event_type="workflow.product_research.card_failed",
            message="A product card could not be auto-researched.",
            article_job_id=job.id,
            level="WARNING",
            metadata_json={"product_source_id": link_id, "error": str(exc)[:300]},
        )

    researched = 0
    failures = 0

    # 1) Research every linked product that is not already draft-ready.
    db.refresh(job)
    for link in [link for link in getattr(job, "article_product_links", []) if link]:
        if getattr(link, "draft_ready", False):
            continue
        try:
            research_product_via_websearch(db, link)
            researched += 1
        except ProductResearchError as exc:
            failures += 1
            _log_card_failure(getattr(link, "id", None), exc)

    # 2) If still below the floor, discover more products (up to the cap) and research them.
    db.refresh(job)
    discovered = 0
    if _draft_ready_count(job) < get_min_products_for_post_type(job.post_type):
        current_links = len([link for link in getattr(job, "article_product_links", []) if link])
        need = MAX_PRODUCT_CARDS - current_links
        if need > 0:
            try:
                new_links = discover_products_via_websearch(db, job, max_products=need)
                discovered = len(new_links)
            except ProductResearchError as exc:
                new_links = []
                create_app_log(
                    db,
                    event_type="workflow.product_research.discovery_failed",
                    message="Automatic product discovery failed.",
                    article_job_id=job.id,
                    level="WARNING",
                    metadata_json={"error": str(exc)[:300]},
                )
            for link in new_links:
                try:
                    research_product_via_websearch(db, link)
                    researched += 1
                except ProductResearchError as exc:
                    failures += 1
                    _log_card_failure(getattr(link, "id", None), exc)

    db.refresh(job)
    draft_ready = _draft_ready_count(job)
    total = len([link for link in getattr(job, "article_product_links", []) if link])
    message = f"Product research complete: {draft_ready} draft-ready card{'s' if draft_ready != 1 else ''} from {total} product{'s' if total != 1 else ''}."
    if discovered:
        message += f" Discovered {discovered} new product{'s' if discovered != 1 else ''} via web search."
    if failures:
        message += f" {failures} card{'s' if failures != 1 else ''} need manual review."
    return {"message": message}


def run_reddit_feedback_research(db: Session, job: ArticleJob) -> dict:
    if not get_settings().openai_api_key:
        return {"message": "Reddit feedback research skipped: OpenAI web search is not configured."}

    try:
        feedback = research_reddit_feedback(db, job)
    except RedditFeedbackError as exc:
        create_app_log(
            db,
            event_type="workflow.reddit_feedback.failed",
            message="Reddit feedback research failed.",
            article_job_id=job.id,
            level="ERROR",
            metadata_json={"error": str(exc)[:500]},
        )
        raise

    _sync_local_export(db, job, "reddit_feedback")
    return {
        "message": (
            f"Reddit feedback research complete. "
            f"Qualified patterns: {len(feedback.get('qualified_patterns') or [])}. "
            f"Rejected patterns: {len(feedback.get('rejected_patterns') or [])}."
        )
    }


def _store_serp_results(db: Session, article_job_id: int, rows: list[dict]) -> None:
    for row in rows:
        db.add(SerpResult(article_job_id=article_job_id, **row))
    db.commit()


def _store_keyword_research(db: Session, article_job_id: int, rows: list[dict]) -> None:
    for row in rows:
        db.add(KeywordResearch(article_job_id=article_job_id, **row))
    db.commit()


def run_serp_research(db: Session, job: ArticleJob) -> dict:
    previous_status = job.status
    create_app_log(
        db,
        event_type="workflow.serp_research.started",
        message="SERP research started.",
        article_job_id=job.id,
        metadata_json={"provider": "DataForSEO", "endpoint": "/v3/serp/google/organic/live/advanced"},
    )
    _save_job(db, job, ArticleJobStatus.RESEARCHING.value)
    try:
        client = DataForSEOClient()
        request_result = client.fetch_google_serp(job.primary_keyword)
        rows, extras = parse_serp_items(request_result.result)
        _store_serp_results(db, job.id, rows)
        _create_cost_log(
            db,
            article_job_id=job.id,
            action="serp_research",
            endpoint=request_result.endpoint,
            cost=request_result.cost,
        )
        _save_job(db, job, ArticleJobStatus.RESEARCH_COMPLETE.value)
        create_app_log(
            db,
            event_type="workflow.serp_research.completed",
            message="SERP research completed.",
            article_job_id=job.id,
            metadata_json={
                "provider": "DataForSEO",
                "endpoint": request_result.endpoint,
                "result_count": len(rows),
                "people_also_ask_count": len(extras["people_also_ask"]),
                "related_searches_count": len(extras["related_searches"]),
                "cost": request_result.cost,
            },
        )
        _sync_local_export(db, job, "serp_research")
        return {
            "action": "run SERP research",
            "article_job_id": job.id,
            "status": job.status,
            "message": f"SERP research completed and saved {len(rows)} results.",
            "next_step": "Generate brief",
        }
    except DataForSEOError as exc:
        _save_job(db, job, previous_status)
        create_app_log(
            db,
            event_type="workflow.serp_research.failed",
            message=f"SERP research failed: {exc}",
            article_job_id=job.id,
            level="ERROR",
            metadata_json={"provider": "DataForSEO"},
        )
        raise
    except Exception:
        _save_job(db, job, previous_status)
        create_app_log(
            db,
            event_type="workflow.serp_research.failed",
            message="SERP research failed due to response parsing or storage.",
            article_job_id=job.id,
            level="ERROR",
            metadata_json={"provider": "DataForSEO"},
        )
        raise DataForSEOError("SERP research failed while processing the DataForSEO response.")


def run_keyword_research(db: Session, job: ArticleJob) -> dict:
    create_app_log(
        db,
        event_type="workflow.keyword_research.started",
        message="Keyword research started.",
        article_job_id=job.id,
        metadata_json={"provider": "DataForSEO", "endpoint": "/v3/dataforseo_labs/google/keyword_suggestions/live"},
    )
    try:
        client = DataForSEOClient()
        request_result = client.fetch_keyword_ideas(job.primary_keyword)
        rows = parse_keyword_ideas(request_result.result)
        _store_keyword_research(db, job.id, rows)
        _create_cost_log(
            db,
            article_job_id=job.id,
            action="keyword_research",
            endpoint=request_result.endpoint,
            cost=request_result.cost,
        )
        create_app_log(
            db,
            event_type="workflow.keyword_research.completed",
            message="Keyword research completed.",
            article_job_id=job.id,
            metadata_json={
                "provider": "DataForSEO",
                "endpoint": request_result.endpoint,
                "result_count": len(rows),
                "cost": request_result.cost,
            },
        )
        _sync_local_export(db, job, "keyword_research")
        return {
            "action": "run keyword research",
            "article_job_id": job.id,
            "status": job.status,
            "message": f"Keyword research completed and saved {len(rows)} rows.",
            "next_step": "Run competitor gap analysis",
        }
    except DataForSEOError as exc:
        create_app_log(
            db,
            event_type="workflow.keyword_research.failed",
            message=f"Keyword research failed: {exc}",
            article_job_id=job.id,
            level="ERROR",
            metadata_json={"provider": "DataForSEO"},
        )
        raise
    except Exception:
        create_app_log(
            db,
            event_type="workflow.keyword_research.failed",
            message="Keyword research failed due to response parsing or storage.",
            article_job_id=job.id,
            level="ERROR",
            metadata_json={"provider": "DataForSEO"},
        )
        raise DataForSEOError("Keyword research failed while processing the DataForSEO response.")


def run_competitor_gap_analysis(db: Session, job: ArticleJob) -> dict:
    _save_job(db, job, ArticleJobStatus.RESEARCH_COMPLETE.value)
    create_app_log(
        db,
        event_type="workflow.competitor_gap_analysis",
        message="Competitor gap analysis stub recorded without external analysis.",
        article_job_id=job.id,
        metadata_json={"provider": "DataForSEO/manual synthesis", "stub": True},
    )
    return {
        "action": "run competitor gap analysis",
        "article_job_id": job.id,
        "status": job.status,
        "message": "Placeholder competitor gap analysis recorded.",
        "next_step": "Run product/review research",
    }


def extract_competitors(db: Session, job: ArticleJob) -> dict:
    create_app_log(
        db,
        event_type="workflow.extract_competitors.started",
        message="Competitor extraction started.",
        article_job_id=job.id,
        metadata_json={"source": "stored_serp_results", "limit": 5},
    )
    try:
        extracted = extract_competitors_for_job(db, job.id)
        failures = sum(1 for row in extracted if row.extraction_status == "failed")
        create_app_log(
            db,
            event_type="workflow.extract_competitors.completed",
            message="Competitor extraction completed.",
            article_job_id=job.id,
            metadata_json={"competitor_count": len(extracted), "failed_count": failures},
        )
        _sync_local_export(db, job, "competitor_extraction")
        return {
            "action": "extract competitors",
            "article_job_id": job.id,
            "status": job.status,
            "message": f"Extracted {len(extracted)} competitor pages with {failures} failures.",
            "next_step": "Analyse SERP",
        }
    except Exception:  # noqa: BLE001
        create_app_log(
            db,
            event_type="workflow.extract_competitors.failed",
            message="Competitor extraction failed.",
            article_job_id=job.id,
            level="ERROR",
            metadata_json={"source": "stored_serp_results"},
        )
        raise


def analyse_serp(db: Session, job: ArticleJob) -> dict:
    create_app_log(
        db,
        event_type="workflow.analyse_serp.started",
        message="SERP analysis started.",
        article_job_id=job.id,
        metadata_json={"source": "stored_serp_and_competitor_data"},
    )
    try:
        report = analyse_serp_for_job(db, job.id)
        create_app_log(
            db,
            event_type="workflow.analyse_serp.completed",
            message="SERP analysis completed.",
            article_job_id=job.id,
            metadata_json={"report_id": report.id, "difficulty_estimate": report.difficulty_estimate},
        )
        _sync_local_export(db, job, "serp_analysis")
        return {
            "action": "analyse serp",
            "article_job_id": job.id,
            "status": job.status,
            "message": "SERP analysis report created.",
            "next_step": "Generate brief",
        }
    except Exception:  # noqa: BLE001
        create_app_log(
            db,
            event_type="workflow.analyse_serp.failed",
            message="SERP analysis failed.",
            article_job_id=job.id,
            level="ERROR",
            metadata_json={"source": "stored_serp_and_competitor_data"},
        )
        raise


def run_product_review_research(db: Session, job: ArticleJob) -> dict:
    _save_job(db, job, ArticleJobStatus.RESEARCH_COMPLETE.value)
    create_app_log(
        db,
        event_type="workflow.product_review_research",
        message="Product/review research stub recorded without external crawling or scraping.",
        article_job_id=job.id,
        metadata_json={"provider": "retailer/review research", "stub": True},
    )
    return {
        "action": "run product/review research",
        "article_job_id": job.id,
        "status": job.status,
        "message": "Placeholder product and review research recorded.",
        "next_step": "Generate brief",
    }


def find_product_candidates(db: Session, job: ArticleJob) -> dict:
    create_app_log(
        db,
        event_type="workflow.product_candidate_discovery.started",
        message="Product candidate discovery started.",
        article_job_id=job.id,
        metadata_json={"source": "stored_research_data_first", "max_paid_searches": 3},
    )
    try:
        candidates, paid_logs = discover_product_candidates(db, job, allow_paid_fallback=True)
        for paid in paid_logs:
            _create_cost_log(
                db,
                article_job_id=job.id,
                action="product_candidate_discovery",
                endpoint=paid["endpoint"],
                cost=paid["cost"],
                request_count=paid.get("request_count", 1),
            )
        create_app_log(
            db,
            event_type="workflow.product_candidate_discovery.completed",
            message="Product candidate discovery completed.",
            article_job_id=job.id,
            metadata_json={
                "candidate_count": len(candidates),
                "paid_search_count": len(paid_logs),
            },
        )
        _sync_local_export(db, job, "product_candidate_discovery")
        return {
            "action": "find product candidates",
            "article_job_id": job.id,
            "status": job.status,
            "message": f"Found {len(candidates)} product candidates.",
            "next_step": "Approve or convert candidate products",
        }
    except DataForSEOError as exc:
        create_app_log(
            db,
            event_type="workflow.product_candidate_discovery.failed",
            message=f"Product candidate discovery failed: {exc}",
            article_job_id=job.id,
            level="ERROR",
            metadata_json={"source": "stored_research_data_and_dataforseo"},
        )
        raise


def approve_candidate(db: Session, candidate) -> dict:
    candidate = approve_product_candidate(db, candidate)
    create_app_log(
        db,
        event_type="workflow.product_candidate.approved",
        message="Product candidate approved.",
        article_job_id=candidate.article_job_id,
        metadata_json={"candidate_id": candidate.id, "product_name": candidate.product_name},
    )
    _sync_local_export(db, candidate.article_job, "product_candidate_approved")
    return {
        "action": "approve product candidate",
        "article_job_id": candidate.article_job_id,
        "status": "ok",
        "message": "Product candidate approved.",
        "next_step": "Create product card",
    }


def ignore_candidate(db: Session, candidate) -> dict:
    candidate = ignore_product_candidate(db, candidate)
    create_app_log(
        db,
        event_type="workflow.product_candidate.ignored",
        message="Product candidate ignored.",
        article_job_id=candidate.article_job_id,
        metadata_json={"candidate_id": candidate.id, "product_name": candidate.product_name},
    )
    _sync_local_export(db, candidate.article_job, "product_candidate_ignored")
    return {
        "action": "ignore product candidate",
        "article_job_id": candidate.article_job_id,
        "status": "ok",
        "message": "Product candidate ignored.",
        "next_step": "Review other candidates",
    }


def convert_candidate(db: Session, candidate, *, auto_extract: bool = True):
    try:
        candidate, link = convert_product_candidate(db, candidate=candidate, auto_extract=auto_extract)
    except ProductCandidateError:
        raise
    create_app_log(
        db,
        event_type="workflow.product_candidate.converted",
        message="Product candidate converted to a linked product card.",
        article_job_id=candidate.article_job_id,
        metadata_json={
            "candidate_id": candidate.id,
            "product_name": candidate.product_name,
            "product_link_id": link.id,
            "product_id": link.product_id,
            "auto_extract": auto_extract,
        },
    )
    _sync_local_export(db, candidate.article_job, "product_candidate_converted")
    return candidate, link


def generate_brief(db: Session, job: ArticleJob) -> dict:
    create_app_log(
        db,
        event_type="workflow.generate_brief.started",
        message="Research brief generation started.",
        article_job_id=job.id,
        metadata_json={"source": "stored_research_data", "prompt_file": _prompt_path("content_brief_prompt.md")},
    )
    try:
        payload = build_research_brief_payload(db, job)
        # Carry forward the most recent SERP intent classification (if any) so the
        # new brief version does not shadow it for downstream drafting/QA, which
        # read the latest brief by created_at.
        previous_brief = db.scalar(
            select(ArticleBrief)
            .where(ArticleBrief.article_job_id == job.id)
            .order_by(desc(ArticleBrief.created_at))
        )
        carried_serp_intent = previous_brief.serp_intent_json if previous_brief else None
        brief = ArticleBrief(
            article_job_id=job.id,
            version=len(job.briefs) + 1,
            brief_markdown=render_research_brief_markdown(payload),
            outline_json=payload,
            serp_intent_json=carried_serp_intent,
        )
        db.add(brief)
        db.commit()
        db.refresh(brief)
        _save_job(db, job, ArticleJobStatus.BRIEF_READY.value)
    except Exception:  # noqa: BLE001
        create_app_log(
            db,
            event_type="workflow.generate_brief.failed",
            message="Research brief generation failed.",
            article_job_id=job.id,
            level="ERROR",
            metadata_json={"source": "stored_research_data"},
        )
        raise
    create_app_log(
        db,
        event_type="workflow.generate_brief.completed",
        message="Research brief generated from stored research data.",
        article_job_id=job.id,
        metadata_json={
            "provider": "deterministic-brief-builder",
            "prompt_file": _prompt_path("content_brief_prompt.md"),
            "brief_id": brief.id,
        },
    )
    _sync_local_export(db, job, "generate_brief")
    return {
        "action": "generate brief",
        "article_job_id": job.id,
        "status": job.status,
        "message": "Research brief generated and saved.",
        "next_step": "Generate draft",
    }


def create_original_value_checklist(db: Session, job: ArticleJob) -> dict:
    _save_job(db, job, ArticleJobStatus.BRIEF_READY.value)
    create_app_log(
        db,
        event_type="workflow.original_value_checklist",
        message="Original value checklist stub recorded for article differentiation.",
        article_job_id=job.id,
        metadata_json={
            "stub": True,
            "checklist": [
                "Australian climate context",
                "running cost discussion",
                "who should avoid this guidance",
            ],
        },
    )
    _sync_local_export(db, job, "original_value_checklist")
    return {
        "action": "create original value checklist",
        "article_job_id": job.id,
        "status": job.status,
        "message": "Placeholder original value checklist recorded.",
        "next_step": "Generate draft",
    }


def generate_draft(db: Session, job: ArticleJob) -> dict:
    readiness = get_drafting_readiness(db, job)
    if not readiness["can_generate_draft"]:
        message = readiness["issues"][0]
        create_app_log(
            db,
            event_type="workflow.generate_draft.blocked",
            message=message,
            article_job_id=job.id,
            level="ERROR",
            metadata_json=readiness,
        )
        raise ArticleDraftingError(message)
    _save_job(db, job, ArticleJobStatus.DRAFTING.value)
    result = generate_ai_draft(db, job)
    _sync_local_export(db, job, "generate_draft")
    return result


def classify_serp_intent(db: Session, job: ArticleJob) -> dict:
    result = classify_ai_serp_intent(db, job)
    _sync_local_export(db, job, "serp_intent")
    return result


def run_australian_human_rewrite(db: Session, job: ArticleJob) -> dict:
    _save_job(db, job, ArticleJobStatus.DRAFTING.value)
    result = run_ai_human_edit(db, job)
    _sync_local_export(db, job, "human_edit")
    return result


def run_qa(db: Session, job: ArticleJob, *, stage: str = "initial") -> dict:
    _save_job(db, job, ArticleJobStatus.QA_RUNNING.value)
    result = run_ai_qa(db, job, stage=stage)
    _sync_local_export(db, job, f"qa_{stage}")
    return result


def run_fix_pass(db: Session, job: ArticleJob) -> dict:
    _save_job(db, job, ArticleJobStatus.DRAFTING.value)
    result = run_ai_fix_pass(db, job)
    _sync_local_export(db, job, "fix_pass")
    return result


def set_manual_review_override(db: Session, job: ArticleJob, enabled: bool) -> dict:
    job.review_override = enabled
    if enabled and job.current_qa_score is not None:
        job.status = ArticleJobStatus.READY_FOR_REVIEW.value
    db.add(job)
    db.commit()
    db.refresh(job)
    create_app_log(
        db,
        event_type="workflow.manual_review_override",
        message=f"Manual review override set to {enabled}.",
        article_job_id=job.id,
        metadata_json={"enabled": enabled},
    )
    _sync_local_export(db, job, "manual_review_override")
    return {
        "action": "set manual review override",
        "article_job_id": job.id,
        "status": job.status,
        "message": "Manual review override updated.",
        "next_step": "Export to WordPress draft" if enabled else "Run QA",
    }


def generate_html_from_draft(db: Session, job: ArticleJob) -> dict:
    """
    Generate HTML file from the latest draft JSON.
    """
    from app.services.local_exports import get_article_export_root, _generate_html_from_latest_draft

    # Get the article export directory
    article_root = get_article_export_root(job)

    if not article_root.exists():
        raise ValueError(f"Article export directory not found: {article_root}")

    # Read latest draft JSON
    latest_json_path = article_root / "drafts" / "latest.json"
    if not latest_json_path.exists():
        raise ValueError("No latest.json found. Generate a draft first.")

    import json
    with open(latest_json_path, 'r', encoding='utf-8') as f:
        latest_draft = json.load(f)

    # Generate HTML (raise errors instead of returning None)
    html_path = _generate_html_from_latest_draft(article_root, latest_draft, raise_on_error=True)

    create_app_log(
        db,
        event_type="workflow.generate_html",
        message=f"HTML file generated: {html_path.name}",
        article_job_id=job.id,
        metadata_json={"html_path": str(html_path)},
    )

    return {
        "action": "generate HTML",
        "article_job_id": job.id,
        "status": job.status,
        "message": f"✓ HTML file generated successfully.\nFile: {html_path.name}\nLocation: {article_root}",
        "next_step": None,
    }


def export_to_wordpress_draft(db: Session, job: ArticleJob) -> dict:
    """
    Upload article to WordPress as a draft using the Node.js upload utility.
    """
    # Check if article has a local export path
    if not job.local_export_path:
        raise ValueError("Article has no local export path. Run the full workflow first to generate a completed draft.")

    article_path = Path(job.local_export_path)
    if not article_path.exists():
        raise ValueError(f"Article export path does not exist: {article_path}")

    readiness = build_publish_readiness(db, job)
    if not readiness["ready"]:
        failed = [check for check in readiness["checks"] if not check["passed"]]
        detail = "; ".join(f"{check['label']}: {check['detail']}" for check in failed[:4])
        raise ValueError(f"Article is not ready for WordPress draft upload. {detail}")

    # Get repository root (2 levels up from apps/api)
    repo_root = Path(__file__).resolve().parents[4]
    upload_script = repo_root / "scripts" / "upload-wordpress.js"

    if not upload_script.exists():
        raise ValueError(f"WordPress upload script not found: {upload_script}")

    # Get WordPress credentials from settings
    settings = get_settings()
    wp_base_url = settings.wordpress_base_url
    wp_username = settings.wordpress_username
    wp_app_password = settings.wordpress_app_password

    if not all([wp_base_url, wp_username, wp_app_password]):
        raise ValueError(
            "Missing WordPress credentials in environment.\n"
            "Required: WORDPRESS_BASE_URL, WORDPRESS_USERNAME, WORDPRESS_APP_PASSWORD\n"
            f"Current values: base_url={wp_base_url}, username={wp_username}, password={'***' if wp_app_password else None}"
        )

    # Call Node.js upload script
    try:
        result = subprocess.run(
            ["node", str(upload_script), "--article", str(article_path)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(repo_root),
            env={
                **os.environ,
                "ANTHROPIC_API_KEY": settings.anthropic_api_key or "",
                "ANTHROPIC_MODEL": settings.anthropic_model or "",
                "ANTHROPIC_VISUAL_MODEL": settings.anthropic_visual_model or "",
                "OPENAI_API_KEY": settings.openai_api_key or "",
                "OPENAI_MODEL": settings.openai_model or "",
                "OPENAI_IMAGE_MODEL": settings.openai_image_model or "",
                "WORDPRESS_BASE_URL": wp_base_url,
                "WORDPRESS_USERNAME": wp_username,
                "WORDPRESS_APP_PASSWORD": wp_app_password,
                "VISUALS_ENABLED": "true" if settings.visuals_enabled else "false",
                "VISUALS_OUTPUT_FORMAT": settings.visuals_output_format or "webp",
            },
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Upload script failed"
            raise RuntimeError(f"WordPress upload failed: {error_msg}")

        # Parse output to extract WordPress post ID and URLs
        output = result.stdout
        wordpress_post_id = None
        edit_link = None
        generated_html_path = None
        visual_assets_folder = None
        featured_media_id = None
        inserted_images = None
        warnings: list[str] = []

        # Try to extract post ID and edit link from output
        for line in output.split('\n'):
            if "WordPress post ID:" in line or "WordPress draft post ID:" in line:
                try:
                    wordpress_post_id = int(line.split(":")[-1].strip())
                except ValueError:
                    pass
            elif "Edit URL:" in line:
                edit_link = line.split(":", 1)[-1].strip()
            elif "Generated HTML path:" in line:
                generated_html_path = line.split(":", 1)[-1].strip()
            elif "Visual assets folder:" in line:
                visual_assets_folder = line.split(":", 1)[-1].strip()
            elif "Featured image media ID:" in line:
                featured_media_id = line.split(":", 1)[-1].strip()
            elif "In-content images inserted:" in line:
                inserted_images = line.split(":", 1)[-1].strip()
            elif line.strip().startswith("Warning:"):
                warnings.append(line.strip())

        # Create WordPress export record
        export = WordPressExport(
            article_job_id=job.id,
            export_status="success",
            wordpress_status="draft",
            wordpress_post_id=wordpress_post_id,
            response_payload={
                "post_id": wordpress_post_id,
                "edit_link": edit_link,
                "generated_html_path": generated_html_path,
                "visual_assets_folder": visual_assets_folder,
                "featured_media_id": featured_media_id,
                "inserted_images": inserted_images,
                "warnings": warnings,
                "output": output,
            },
        )
        db.add(export)
        db.commit()

        _save_job(db, job, ArticleJobStatus.EXPORTED_TO_WORDPRESS.value)

        create_app_log(
            db,
            event_type="workflow.export_wordpress_draft",
            message=f"WordPress draft created successfully. Post ID: {wordpress_post_id or 'Unknown'}",
            article_job_id=job.id,
            metadata_json={
                "provider": "WordPress",
                "post_id": wordpress_post_id,
                "status": "draft",
                "edit_link": edit_link,
                "generated_html_path": generated_html_path,
                "visual_assets_folder": visual_assets_folder,
                "featured_media_id": featured_media_id,
                "inserted_images": inserted_images,
                "warnings": warnings,
            },
        )

        success_message = f"✓ WordPress draft post created successfully.\n"
        if wordpress_post_id:
            success_message += f"Post ID: {wordpress_post_id}\n"
        if edit_link:
            success_message += f"Edit URL: {edit_link}\n"
        if featured_media_id:
            success_message += f"Featured image media ID: {featured_media_id}\n"
        if inserted_images is not None:
            success_message += f"In-content images inserted: {inserted_images}\n"
        if generated_html_path:
            success_message += f"Generated HTML path: {generated_html_path}\n"
        if visual_assets_folder:
            success_message += f"Visual assets folder: {visual_assets_folder}\n"
        if warnings:
            success_message += "\n".join(warnings) + "\n"
        success_message += f"Article folder: {article_path}\n"
        success_message += "⚠ This post is a DRAFT only. No content has been published."

        return {
            "action": "export to WordPress draft",
            "article_job_id": job.id,
            "status": job.status,
            "message": success_message,
            "next_step": None,
            "wordpress_post_id": wordpress_post_id,
            "edit_link": edit_link,
        }

    except subprocess.TimeoutExpired:
        raise RuntimeError("WordPress upload timed out after 300 seconds.")
    except Exception as e:
        # Create failed export record
        export = WordPressExport(
            article_job_id=job.id,
            export_status="failed",
            wordpress_status="draft",
            response_payload={"error": str(e)},
        )
        db.add(export)
        db.commit()

        create_app_log(
            db,
            event_type="workflow.export_wordpress_draft_failed",
            message=f"WordPress export failed: {str(e)}",
            article_job_id=job.id,
            metadata_json={"provider": "WordPress", "error": str(e)},
        )

        raise


def run_full_workflow(db: Session, job: ArticleJob, *, research_mode: str) -> WorkflowRun:
    create_app_log(
        db,
        event_type="workflow.full_draft.started",
        message="Full draft workflow started.",
        article_job_id=job.id,
        metadata_json={"research_mode": research_mode},
    )
    run = _create_workflow_run(
        db,
        article_job_id=job.id,
        workflow_mode="full_draft",
        research_mode=research_mode,
    )
    steps = {
        key: _create_workflow_step(db, workflow_run_id=run.id, step_key=key, step_label=label)
        for key, label in WORKFLOW_STEP_SPECS
    }
    workflow_state = get_workflow_state(db, job)
    step_state_map = {step["step_key"]: step for step in workflow_state["steps"]}
    forced_rerun_steps: set[str] = set()

    if research_mode not in {"fresh", "resume_current", "reuse_existing", "refresh_missing_only"}:
        research_mode = "resume_current"
        run.research_mode = research_mode
        db.add(run)
        db.commit()
        db.refresh(run)

    def should_skip(step_key: str) -> tuple[bool, str]:
        if step_key == "fix_pass" and not needs_fix_pass and not job.review_override:
            return True, "Skipped: QA passed or found no actionable issues for a fix pass."
        if step_key == "qa_recheck" and (not needs_fix_pass or not fix_pass_completed) and not job.review_override:
            return True, "Skipped because no fix pass ran."
        if step_key == "qa_recheck" and needs_fix_pass and fix_pass_completed:
            return False, ""
        if (
            step_key == "qa"
            and step_state_map.get("qa", {}).get("status") == "failed"
            and step_state_map.get("fix_pass", {}).get("status") in {"missing", "stale"}
            and step_key not in forced_rerun_steps
        ):
            return True, "Reusing the latest failed QA report so the workflow can continue with a fix pass."
        if research_mode == "fresh":
            return False, ""
        if step_key in forced_rerun_steps:
            return False, ""

        state = step_state_map.get(step_key, {"status": "missing"})
        state_status = state["status"]
        label = steps[step_key].step_label.lower()

        if research_mode == "resume_current":
            if state_status in {"complete", "not_required"}:
                return True, f"Reused current {label}."
            return False, ""
        if research_mode == "reuse_existing":
            if state_status in {"complete", "stale", "not_required"}:
                return True, f"Reused existing {label}."
            return False, ""
        if research_mode == "refresh_missing_only":
            if state_status in {"complete", "not_required"}:
                return True, f"Skipped because {label} is already current."
            return False, ""
        return False, ""

    operations = [
        ("serp_research", lambda: run_serp_research(db, job)),
        ("keyword_research", lambda: run_keyword_research(db, job)),
        ("competitor_extraction", lambda: extract_competitors(db, job)),
        ("serp_analysis", lambda: analyse_serp(db, job)),
        ("serp_intent", lambda: classify_serp_intent(db, job)),
        ("research_brief", lambda: generate_brief(db, job)),
        ("product_research", lambda: run_product_research(db, job)),
        ("reddit_feedback", lambda: run_reddit_feedback_research(db, job)),
        ("draft_generation", lambda: generate_draft(db, job)),
        ("human_edit", lambda: run_australian_human_rewrite(db, job)),
        ("qa", lambda: run_qa(db, job, stage="initial")),
        ("fix_pass", lambda: run_ai_fix_pass(db, job)),
        ("qa_recheck", lambda: run_qa(db, job, stage="recheck")),
    ]

    fix_pass_status = step_state_map.get("fix_pass", {}).get("status")
    qa_status = step_state_map.get("qa", {}).get("status")
    qa_recheck_status = step_state_map.get("qa_recheck", {}).get("status")
    fix_pass_waiting_for_recheck = (
        fix_pass_status in {"complete", "stale"}
        and qa_recheck_status in {"missing", "stale", "failed"}
        and qa_status in {"failed", "stale"}
    )
    needs_fix_pass = fix_pass_status in {"missing", "stale"} or fix_pass_waiting_for_recheck
    fix_pass_completed = fix_pass_waiting_for_recheck

    try:
        for step_key, operation in operations:
            step = steps[step_key]
            _save_workflow_run(db, run, status="running", current_step=step_key)
            skip, skip_message = should_skip(step_key)
            if skip:
                _update_workflow_step(db, step, status="skipped", message=skip_message)
                if step_key == "fix_pass" and needs_fix_pass:
                    # A reused fix pass still needs verification. Without this,
                    # resumed batch runs can stop after "Reused current fix pass"
                    # and leave the latest failed QA report as the source of truth.
                    fix_pass_completed = True
                create_app_log(
                    db,
                    event_type=f"workflow.full_draft.{step_key}.skipped",
                    message=skip_message,
                    article_job_id=job.id,
                    metadata_json={"workflow_run_id": run.id, "research_mode": research_mode},
                )
                continue
            if step_key == "draft_generation":
                readiness = get_drafting_readiness(db, job)
                if not readiness["can_generate_draft"]:
                    blocked_message = readiness["issues"][0]
                    _update_workflow_step(db, step, status="skipped", message=f"Blocked: {blocked_message}")
                    for remaining_key in ("human_edit", "qa", "fix_pass", "qa_recheck"):
                        remaining_step = steps[remaining_key]
                        if remaining_step.status == "pending":
                            _update_workflow_step(
                                db,
                                remaining_step,
                                status="skipped",
                                message="Skipped because draft generation was blocked.",
                            )
                    _save_workflow_run(db, run, status="failed", current_step=step_key, summary_message=blocked_message)
                    create_app_log(
                        db,
                        event_type="workflow.full_draft.draft_generation.blocked",
                        message=blocked_message,
                        article_job_id=job.id,
                        level="ERROR",
                        metadata_json={"workflow_run_id": run.id, **readiness},
                    )
                    create_app_log(
                        db,
                        event_type="workflow.full_draft.failed",
                        message="Full draft workflow stopped before draft generation.",
                        article_job_id=job.id,
                        level="ERROR",
                        metadata_json={"workflow_run_id": run.id, "step_key": step_key},
                    )
                    _sync_local_export(db, job, "full_workflow_blocked")
                    return run

            _update_workflow_step(db, step, status="running", message=f"{step.step_label} running.")
            create_app_log(
                db,
                event_type=f"workflow.full_draft.{step_key}.started",
                message=f"{step.step_label} started.",
                article_job_id=job.id,
                metadata_json={"workflow_run_id": run.id},
            )
            try:
                result = operation()
            except Exception as exc:  # noqa: BLE001
                failure_message = str(exc) or f"{step.step_label} failed."
                _update_workflow_step(db, step, status="failed", message=failure_message)
                _save_workflow_run(db, run, status="failed", current_step=step_key, summary_message=failure_message)
                create_app_log(
                    db,
                    event_type=f"workflow.full_draft.{step_key}.failed",
                    message=f"{step.step_label} failed: {failure_message}",
                    article_job_id=job.id,
                    level="ERROR",
                    metadata_json={"workflow_run_id": run.id},
                )
                create_app_log(
                    db,
                    event_type="workflow.full_draft.failed",
                    message=f"Full draft workflow failed at {step.step_label}.",
                    article_job_id=job.id,
                    level="ERROR",
                    metadata_json={"workflow_run_id": run.id, "step_key": step_key},
                )
                _sync_local_export(db, job, "full_workflow_failed")
                raise

            _update_workflow_step(db, step, status="complete", message=result["message"])
            create_app_log(
                db,
                event_type=f"workflow.full_draft.{step_key}.completed",
                message=f"{step.step_label} completed.",
                article_job_id=job.id,
                metadata_json={"workflow_run_id": run.id},
            )
            forced_rerun_steps.update(DOWNSTREAM_INVALIDATION.get(step_key, set()))
            if step_key == "qa" and job.status == ArticleJobStatus.QA_FAILED.value and not job.review_override:
                # Only run a fix pass when QA produced actionable issues; otherwise
                # leave QA failed rather than burn a fix-pass rewrite on vague notes.
                if _qa_findings_actionable(_latest_qa_findings(db, job.id)):
                    needs_fix_pass = True
                else:
                    needs_fix_pass = False
                    create_app_log(
                        db,
                        event_type="workflow.full_draft.fix_pass.not_actionable",
                        message="Fix pass skipped: QA found no actionable issues to fix.",
                        article_job_id=job.id,
                        metadata_json={"workflow_run_id": run.id},
                    )
            if step_key == "fix_pass":
                fix_pass_completed = True
            if step_key == "qa_recheck" and needs_fix_pass and fix_pass_completed and job.status == ArticleJobStatus.QA_FAILED.value and not job.review_override:
                _save_workflow_run(db, run, status="failed", current_step="qa_recheck", summary_message="QA score remained below threshold.")
                create_app_log(
                    db,
                    event_type="workflow.full_draft.failed",
                    message="Full draft workflow failed after QA recheck.",
                    article_job_id=job.id,
                    level="ERROR",
                    metadata_json={"workflow_run_id": run.id, "step_key": "qa_recheck"},
                )
                _sync_local_export(db, job, "full_workflow_failed")
                return run

        usage_summary = _summarise_run_usage(db, job.id, run.created_at)
        create_app_log(
            db,
            event_type="workflow.full_draft.usage_summary",
            message=(
                f"AI usage this run: {usage_summary['ai_calls']} calls, "
                f"~{usage_summary['input_tokens']} input / {usage_summary['output_tokens']} output tokens "
                f"(cache read {usage_summary['cache_read_tokens']}, cache write {usage_summary['cache_write_tokens']})."
            ),
            article_job_id=job.id,
            metadata_json={"workflow_run_id": run.id, **usage_summary},
        )
        _save_workflow_run(db, run, status="complete", current_step=None, summary_message="Full draft workflow completed.")
        create_app_log(
            db,
            event_type="workflow.full_draft.completed",
            message="Full draft workflow completed.",
            article_job_id=job.id,
            metadata_json={"workflow_run_id": run.id},
        )
        _sync_local_export(db, job, "full_workflow_completed")
        return run
    except Exception:
        raise
