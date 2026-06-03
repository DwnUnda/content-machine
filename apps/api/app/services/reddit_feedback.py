from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.entities import ArticleJob, Product
from app.services.logging import create_app_log

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
PROMPT_NAME = "reddit_feedback_prompt.md"
MIN_COMMENT_COUNT = 3
MIN_THREAD_COUNT = 2
ALLOWED_CONFIDENCE = {"moderate", "strong"}


class RedditFeedbackError(Exception):
    pass


def _read_prompt() -> str:
    return (PROMPTS_DIR / PROMPT_NAME).read_text(encoding="utf-8")


def _clean_text(value: object, limit: int | None = None) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[:limit] if limit and text else text


def _is_reddit_url(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return False
    return host.endswith("reddit.com")


def _product_payload(job: ArticleJob) -> list[dict]:
    products: list[dict] = []
    for link in getattr(job, "article_product_links", []) or []:
        product = getattr(link, "product", None)
        if not product:
            continue
        products.append(
            {
                "id": product.id,
                "name": product.name,
                "brand": product.brand,
                "model_number": product.model_number,
                "category": product.category,
                "role": product.role,
            }
        )
    return products[:8]


def _normalise_source(entry: object) -> dict | None:
    if not isinstance(entry, dict):
        return None
    url = _clean_text(entry.get("url"), 1000)
    if not url or not _is_reddit_url(url):
        return None
    return {
        "url": url,
        "subreddit": _clean_text(entry.get("subreddit"), 120) or None,
        "used_for": _clean_text(entry.get("used_for"), 300) or None,
    }


def _normalise_pattern(entry: object) -> dict | None:
    if not isinstance(entry, dict):
        return None

    comment_count = _safe_int(entry.get("evidence_comment_count"))
    thread_count = _safe_int(entry.get("evidence_thread_count"))
    confidence = _clean_text(entry.get("confidence"), 40).lower()
    source_urls = [
        url
        for url in (_clean_text(url, 1000) for url in (entry.get("source_urls") or []))
        if url and _is_reddit_url(url)
    ]

    if comment_count < MIN_COMMENT_COUNT and thread_count < MIN_THREAD_COUNT:
        return None
    if confidence not in ALLOWED_CONFIDENCE:
        return None
    if not source_urls:
        return None

    wording = _clean_text(entry.get("publishable_wording"), 500)
    issue = _clean_text(entry.get("issue"), 220)
    if not wording or not issue:
        return None

    return {
        "product_name": _clean_text(entry.get("product_name"), 255) or "Category-level feedback",
        "issue": issue,
        "feedback_type": _clean_text(entry.get("feedback_type"), 80) or "other",
        "sentiment": _clean_text(entry.get("sentiment"), 40) or "mixed",
        "evidence_comment_count": comment_count,
        "evidence_thread_count": thread_count,
        "confidence": confidence,
        "not_trivially_fixed_reason": _clean_text(entry.get("not_trivially_fixed_reason"), 400),
        "publishable_wording": wording,
        "source_urls": source_urls[:5],
    }


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        return int(digits) if digits else 0


def _normalise_rejected(entry: object) -> dict | None:
    if not isinstance(entry, dict):
        return None
    issue = _clean_text(entry.get("issue"), 220)
    if not issue:
        return None
    return {
        "product_name": _clean_text(entry.get("product_name"), 255) or "Category-level feedback",
        "issue": issue,
        "reason_rejected": _clean_text(entry.get("reason_rejected"), 300) or "unsupported",
    }


def normalise_reddit_feedback_payload(payload: dict) -> dict:
    qualified = [
        pattern
        for pattern in (_normalise_pattern(item) for item in (payload.get("qualified_patterns") or []))
        if pattern
    ]
    rejected = [
        pattern
        for pattern in (_normalise_rejected(item) for item in (payload.get("rejected_patterns") or []))
        if pattern
    ]
    sources = [
        source
        for source in (_normalise_source(item) for item in (payload.get("research_sources") or []))
        if source
    ]

    return {
        "searched": bool(payload.get("searched", True)),
        "query_summary": _clean_text(payload.get("query_summary"), 500),
        "products_considered": [
            _clean_text(item, 255)
            for item in (payload.get("products_considered") or [])
            if _clean_text(item)
        ],
        "qualified_patterns": qualified,
        "rejected_patterns": rejected,
        "research_sources": sources,
        "notes": _clean_text(payload.get("notes"), 500)
        or "Reddit is treated as anecdotal owner feedback only, not as a source for specifications.",
        "policy": {
            "minimum_comments": MIN_COMMENT_COUNT,
            "minimum_threads": MIN_THREAD_COUNT,
            "reddit_only_for": "owner feedback patterns, not specs/prices/safety/medical claims",
        },
    }


def _product_matches(product: Product, product_name: str) -> bool:
    target = product_name.lower()
    candidates = [product.name, product.brand, product.model_number]
    return any(value and str(value).lower() in target for value in candidates)


def _append_unique(existing: str | None, additions: list[str]) -> str | None:
    current = _clean_text(existing)
    parts = [part.strip() for part in current.split(";") if part.strip()] if current else []
    seen = {part.lower() for part in parts}
    for addition in additions:
        cleaned = _clean_text(addition)
        if cleaned and cleaned.lower() not in seen:
            parts.append(cleaned)
            seen.add(cleaned.lower())
    return "; ".join(parts) if parts else existing


def apply_reddit_feedback_to_products(db: Session, job: ArticleJob, feedback: dict) -> int:
    patterns = feedback.get("qualified_patterns") if isinstance(feedback, dict) else []
    if not isinstance(patterns, list) or not patterns:
        return 0

    products = [link.product for link in getattr(job, "article_product_links", []) or [] if getattr(link, "product", None)]
    updated = 0
    for product in products:
        product_patterns = [
            pattern
            for pattern in patterns
            if isinstance(pattern, dict) and _product_matches(product, str(pattern.get("product_name") or ""))
        ]
        if not product_patterns:
            continue

        additions = [str(pattern["publishable_wording"]) for pattern in product_patterns if pattern.get("publishable_wording")]
        product.negative_review_patterns = _append_unique(product.negative_review_patterns, additions)
        reliability_additions = [
            str(pattern["publishable_wording"])
            for pattern in product_patterns
            if pattern.get("feedback_type") in {"reliability", "support", "running_cost"}
        ]
        if reliability_additions:
            product.reliability_concerns = _append_unique(product.reliability_concerns, reliability_additions)

        raw = product.raw_extracted_json if isinstance(product.raw_extracted_json, dict) else {}
        raw["reddit_feedback"] = product_patterns
        product.raw_extracted_json = raw
        db.add(product)
        updated += 1

    if updated:
        db.commit()
    return updated


def research_reddit_feedback(db: Session, job: ArticleJob) -> dict:
    from app.services.openai_client import OpenAIClient, OpenAIError, web_search_fired

    products = _product_payload(job)
    input_text = (
        f"ARTICLE_TOPIC: {job.title}\n"
        f"PRIMARY_KEYWORD: {job.primary_keyword}\n"
        f"POST_TYPE: {job.post_type}\n"
        f"PRODUCTS: {products if products else '(none; search category-level Reddit discussions)'}"
    )

    try:
        client = OpenAIClient()
        response = client.generate_json_with_web_search(
            instructions=_read_prompt(),
            input_text=input_text,
            max_output_tokens=5000,
        )
    except OpenAIError as exc:
        raise RedditFeedbackError(f"Reddit feedback search failed: {exc}") from exc

    payload = response.parsed_json if isinstance(response.parsed_json, dict) else {}
    feedback = normalise_reddit_feedback_payload(payload)
    feedback["provider"] = "openai_web_search"
    feedback["web_search_fired"] = web_search_fired(response.response_json)

    updated_products = apply_reddit_feedback_to_products(db, job, feedback)
    create_app_log(
        db,
        event_type="workflow.reddit_feedback.completed",
        message=(
            f"Reddit feedback research completed: "
            f"{len(feedback['qualified_patterns'])} qualified pattern(s), "
            f"{len(feedback['rejected_patterns'])} rejected pattern(s)."
        ),
        article_job_id=job.id,
        metadata_json={**feedback, "updated_products": updated_products},
    )
    return {**feedback, "updated_products": updated_products}
