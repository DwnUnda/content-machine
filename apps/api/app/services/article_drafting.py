from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.entities import (
    ArticleBrief,
    ArticleDraft,
    ArticleJob,
    PostType,
    ArticleJobStatus,
    AppLog,
    AppSetting,
    CompetitorAnalysisReport,
    CompetitorPage,
    KeywordResearch,
    Product,
    QaReport,
    SerpResult,
)
from app.services.anthropic_client import AnthropicClient, AnthropicError
from app.services.content_rules import get_qa_threshold
from app.services.logging import create_app_log
from app.services.openai_client import OpenAIClient, OpenAIError
from app.services.post_type_generation_rules import get_post_type_generation_rules


PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
NOT_CONFIRMED = "Not confirmed"
MAX_BRIEF_MARKDOWN_CHARS = 2400
MAX_TEXT_SNIPPET_CHARS = 600
MAX_PRODUCT_FIELD_CHARS = 360
MAX_PRODUCT_LONG_FIELD_CHARS = 520
MAX_PRODUCT_LIST_ITEMS = 8
MAX_PRODUCT_SPEC_ITEMS = 12
# Output token caps. Commercial posts now carry richer HTML modules, top-pick
# cards, jump links, renderer metadata and deeper review sections, so the old
# 16k ceiling is no longer sufficient for the longest buyer guides.
MAX_CLAUDE_OUTPUT_TOKENS = 12000
MAX_CLAUDE_REPAIR_TOKENS = 10000
DRAFT_OUTPUT_TOKEN_CAPS = {
    PostType.INFORMATIONAL_BLOG.value: 12000,
    PostType.SINGLE_PRODUCT_REVIEW.value: 20000,
    PostType.PRODUCT_COMPARISON.value: 22000,
    PostType.MONEY_POST.value: 24000,
    PostType.BEST_X_FOR_Y.value: 24000,
}
HTML_SOURCE_POST_TYPES = {
    PostType.MONEY_POST.value,
    PostType.SINGLE_PRODUCT_REVIEW.value,
    PostType.PRODUCT_COMPARISON.value,
    PostType.BEST_X_FOR_Y.value,
}
FINAL_RECOMMENDATION_HEADINGS = (
    "## Final Recommendation",
    "## Final Thoughts",
    "## Conclusion",
)
FAQ_SECTION_HEADINGS = (
    "## FAQ",
    "## Frequently Asked Questions",
    "## Frequently asked questions",
)
MINIMUM_WORD_COUNTS = {
    PostType.MONEY_POST.value: 2500,
    PostType.BEST_X_FOR_Y.value: 2000,
    PostType.SINGLE_PRODUCT_REVIEW.value: 1500,
    PostType.PRODUCT_COMPARISON.value: 1500,
    PostType.INFORMATIONAL_BLOG.value: 1200,
}


def _draft_max_output_tokens(job: ArticleJob) -> int:
    """Output token cap for a drafting pass, sized to the article type."""
    return DRAFT_OUTPUT_TOKEN_CAPS.get(job.post_type, MAX_CLAUDE_OUTPUT_TOKENS)


def _uses_html_source_format(post_type: str) -> bool:
    return post_type in HTML_SOURCE_POST_TYPES


def _required_tail_section_markers(post_type: str) -> list[str]:
    if _uses_html_source_format(post_type):
        return ["faq-section", "final-verdict"]
    return ["## Frequently asked questions", "## Final thoughts"]


def _repair_tail_instruction(post_type: str) -> str:
    if _uses_html_source_format(post_type):
        return (
            "Include the faq-section and final-verdict sections as specified in post_type_generation_rules. "
            'CRITICAL: Your draft_markdown MUST include <section class="faq-section"> and '
            '<section class="final-verdict"> as defined in post_type_generation_rules. '
        )
    return (
        "Include the FAQ and final thoughts sections as specified in post_type_generation_rules. "
        'CRITICAL: Your draft_markdown MUST include a "## Frequently asked questions" section and a '
        '"## Final thoughts" section as defined in post_type_generation_rules. '
    )


def _looks_like_unparsed_json_draft(markdown: str | None) -> bool:
    """True if a draft body is actually a raw, unparsed JSON blob.

    When a JSON response is truncated mid-string the parser falls back to wrapping
    the raw text, so the saved 'article' starts with `{"draft_markdown"` and is
    littered with literal \\n escapes. We must never treat that as a valid draft.
    """
    head = (markdown or "").lstrip()[:400]
    if head.startswith("{") and '"draft_markdown"' in head:
        return True
    # A genuine markdown body uses real newlines; a high density of literal \n
    # escape sequences with almost no real newlines indicates an unparsed blob.
    if markdown and markdown.count("\\n") > 15 and markdown.count("\n") < 5:
        return True
    return False


def _assert_ai_output_complete(client, *, markdown: str | None, stage: str) -> None:
    """Reject truncated or JSON-corrupted AI output before it is saved.

    Raises ArticleDraftingError so the calling step is marked failed and the
    workflow stops, instead of saving a corrupted draft that would trigger
    expensive QA, fix and re-run cycles.
    """
    stop_reason = getattr(client, "last_stop_reason", None)
    parse_ok = getattr(client, "last_parse_ok", True)
    if stop_reason == "max_tokens":
        raise ArticleDraftingError(
            f"{stage} output was truncated: the model reached its maximum output token limit. "
            "The draft was not saved. Increase the output cap or reduce the requested length."
        )
    if not parse_ok or _looks_like_unparsed_json_draft(markdown):
        raise ArticleDraftingError(
            f"{stage} output was corrupted and could not be parsed as valid JSON "
            "(most likely truncated). The draft was not saved."
        )
INTERNAL_LINK_DRAFT_WARNING = (
    "No internal links were included. This is acceptable for draft generation, "
    "but internal link opportunities should be reviewed before publishing once related content exists."
)


class ArticleDraftingError(Exception):
    pass


@dataclass(slots=True)
class DraftPayload:
    draft_markdown: str
    seo_title: str | None = None
    meta_description: str | None = None
    slug: str | None = None
    excerpt: str | None = None
    notes: list[str] | None = None
    title_options: list[str] | None = None
    content_modules: list[dict] | None = None


COMMERCIAL_MODULE_BLUEPRINTS = {
    PostType.MONEY_POST.value: [
        ("top_picks", ("Top picks",)),
        ("comparison", ("Quick comparison",)),
        ("jump_links", ("Jump links",)),
        ("decision_grid", ("Which one should you buy?", "Which one suits your situation?")),
        ("methodology", ("How we chose these products",)),
        ("product_reviews", ("Recommended air purifiers for mould — full reviews", "Our top picks")),
        ("buyer_guide", ("How to choose",)),
        ("mistakes", ("Common mistakes to avoid",)),
        ("faq", ("Frequently asked questions", "FAQ")),
        ("final_verdict", ("Final recommendation", "Final thoughts")),
    ],
    PostType.SINGLE_PRODUCT_REVIEW.value: [
        ("specs", ("Key specifications",)),
        ("performance", ("Real-world performance",)),
        ("comparison", ("How it compares to alternatives",)),
        ("review_fit", ("Who should buy this", "Who should look elsewhere")),
        ("faq", ("Frequently asked questions", "FAQ")),
        ("final_verdict", ("Final verdict", "Bottom line", "Final recommendation")),
    ],
    PostType.PRODUCT_COMPARISON.value: [
        ("comparison", ("Head-to-head comparison",)),
        ("decision_grid", ("Which one wins for your situation?", "Which one should you buy?")),
        ("buyer_guide", ("How to choose between them",)),
        ("faq", ("Frequently asked questions", "FAQ")),
        ("final_verdict", ("Final verdict", "Final recommendation")),
    ],
    PostType.BEST_X_FOR_Y.value: [
        ("top_picks", ("Top picks",)),
        ("comparison", ("Quick comparison",)),
        ("jump_links", ("Jump links",)),
        ("decision_grid", ("Which one suits your situation?", "Which one should you buy?")),
        ("methodology", ("How we chose these products",)),
        ("context", ("Why the right product matters for",)),
        ("product_reviews", ("Recommended air purifiers for mould — full reviews", "Best")),
        ("buyer_guide", ("How to choose for", "How to choose")),
        ("mistakes", ("Common mistakes when buying for", "Common mistakes to avoid")),
        ("faq", ("Frequently asked questions", "FAQ")),
        ("final_verdict", ("Final recommendation", "Final thoughts")),
    ],
}


def _prompt_path(name: str) -> str:
    return str(PROMPTS_DIR / name)


def _read_prompt(name: str) -> str:
    return Path(_prompt_path(name)).read_text(encoding="utf-8")


def _latest_record(db: Session, model: type, article_job_id: int):
    return db.scalar(
        select(model)
        .where(model.article_job_id == article_job_id)
        .order_by(desc(model.created_at))
    )


def _content_rule_map(db: Session) -> dict[str, str]:
    rows = db.scalars(select(AppSetting).where(AppSetting.category == "content_rules")).all()
    return {row.key: row.value or "" for row in rows}


def _sanitise_value(value, limit: int = MAX_PRODUCT_FIELD_CHARS):
    if value is None or value == "":
        return NOT_CONFIRMED
    text = str(value).strip()
    if not text:
        return NOT_CONFIRMED
    return _truncate_text(text, limit) or NOT_CONFIRMED


def _truncate_text(value: str | None, limit: int = MAX_TEXT_SNIPPET_CHARS) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _count_words(value: str | None) -> int:
    if not value:
        return 0
    return len([word for word in value.split() if word.strip()])


def _normalise_content_modules(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    modules: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        module_type = str(item.get("module_type") or item.get("type") or "").strip()
        heading = str(item.get("heading") or "").strip()
        if not module_type or not heading:
            continue
        modules.append({"module_type": module_type, "heading": heading})
    return modules


def _infer_content_modules(draft_markdown: str, post_type: str) -> list[dict]:
    blueprints = COMMERCIAL_MODULE_BLUEPRINTS.get(post_type)
    if not blueprints:
        return []
    lowered = draft_markdown.lower()
    modules: list[dict] = []
    for module_type, heading_candidates in blueprints:
        for candidate in heading_candidates:
            candidate_text = str(candidate).strip()
            if not candidate_text:
                continue
            if candidate_text.lower() in lowered:
                modules.append({"module_type": module_type, "heading": candidate_text})
                break
    if post_type in {PostType.MONEY_POST.value, PostType.BEST_X_FOR_Y.value}:
        if "top-picks-grid" in lowered and not any(item["module_type"] == "top_picks" for item in modules):
            modules.append({"module_type": "top_picks", "heading": "Top picks"})
        if "<article" in lowered and not any(item["module_type"] == "jump_links" for item in modules):
            modules.append({"module_type": "jump_links", "heading": "Jump links"})
    return modules


def _contains_heading(text: str, headings: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(heading.lower() in lowered for heading in headings)


def _find_heading_index(text: str, heading: str) -> int:
    lowered = text.lower()
    return lowered.find(heading.lower())


def _has_faq_section(text: str) -> bool:
    lowered = text.lower()
    return "faq-section" in lowered or _contains_heading(text, FAQ_SECTION_HEADINGS)


def _draft_completion_issues(draft_markdown: str, job: ArticleJob) -> list[str]:
    issues: list[str] = []
    minimum_word_count = MINIMUM_WORD_COUNTS.get(job.post_type)
    word_count = _count_words(draft_markdown)
    if minimum_word_count is not None and word_count < minimum_word_count:
        issues.append(f"Draft is too short. Minimum {minimum_word_count} words required for {job.post_type}.")
    lowered = draft_markdown.lower()
    if not _has_faq_section(draft_markdown):
        issues.append("Missing FAQ section.")
    if "final-verdict" not in lowered and not _contains_heading(draft_markdown, FINAL_RECOMMENDATION_HEADINGS):
        issues.append("Missing final recommendation section.")

    stripped = draft_markdown.rstrip()
    if stripped and not stripped.endswith((".", "!", "?", "\"", "'", ")", "]", ">")):
        last_lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        if last_lines:
            last_line = last_lines[-1]
            if re.match(r"^(?:[-*]|\d+\.)\s+\S{0,30}$", last_line):
                issues.append("Draft ends abruptly in a list item.")
            elif len(last_line.split()) < 5:
                issues.append("Draft appears to end mid-thought.")
    return issues


def _extract_tail_block(draft_markdown: str) -> str:
    lowered = draft_markdown.lower()
    # HTML articles use <section class="faq-section">; markdown fallback: ## FAQ
    for marker in ('<section class="faq-section"',) + tuple(heading.lower() for heading in FAQ_SECTION_HEADINGS):
        idx = lowered.find(marker)
        if idx != -1:
            return draft_markdown[idx:].lstrip()
    for heading in FINAL_RECOMMENDATION_HEADINGS:
        idx = lowered.find(heading.lower())
        if idx != -1:
            return draft_markdown[idx:].lstrip()
    return draft_markdown.strip()


def _repair_draft_tail(db: Session, job: ArticleJob, context: dict, current_markdown: str, *, stage: str) -> str:
    client = AnthropicClient()
    response = client.generate_json(
        system_prompt=(
            _read_prompt("article_draft_prompt.md")
            + "\n\nYou are repairing the ending of an existing Home Dry Lab draft. "
            "Write only the missing tail of the article. "
            + _repair_tail_instruction(job.post_type)
            + "Do not repeat earlier sections. Do not add a new intro. "
            "Return JSON only."
        ),
        user_prompt=json.dumps(
            _build_repair_input(context, current_markdown, stage=stage),
            indent=2,
            ensure_ascii=False,
        ),
        max_tokens=MAX_CLAUDE_REPAIR_TOKENS,
    )
    payload = _draft_payload_from_response(response)
    tail = payload.draft_markdown.strip()
    if not tail:
        raise ArticleDraftingError("Repair response did not include any draft text.")
    tail = _extract_tail_block(tail)
    tail_lower = tail.lower()
    if not _has_faq_section(tail):
        raise ArticleDraftingError("Repair response did not include the FAQ section.")
    if "final-verdict" not in tail_lower and not _contains_heading(tail, FINAL_RECOMMENDATION_HEADINGS):
        raise ArticleDraftingError("Repair response did not include a final recommendation section.")

    lowered_current = current_markdown.lower()
    prefix_index = -1
    markers = ['<section class="faq-section"'] if _uses_html_source_format(job.post_type) else []
    markers.extend(heading.lower() for heading in FAQ_SECTION_HEADINGS)
    for marker in markers:
        prefix_index = lowered_current.find(marker)
        if prefix_index != -1:
            break
    if prefix_index == -1:
        prefix = current_markdown.rstrip()
        combined = prefix + "\n\n" + tail.lstrip()
    else:
        combined = current_markdown[:prefix_index].rstrip() + "\n\n" + tail.lstrip()
    return combined.strip()


def _finalise_draft_markdown(db: Session, job: ArticleJob, context: dict, draft_markdown: str, *, stage: str) -> str:
    cleaned = draft_markdown.strip()
    issues = _draft_completion_issues(cleaned, job)
    if not issues:
        return cleaned
    repaired = _repair_draft_tail(db, job, context, cleaned, stage=stage)
    repair_issues = _draft_completion_issues(repaired, job)
    if repair_issues:
        raise ArticleDraftingError("; ".join(repair_issues))
    return repaired


def _competitor_patterns_summary(competitor_rows: list, limit: int = 5) -> list[dict]:
    """Compact competitor signal for prompts: structure/angles only, never raw body text.

    Built entirely from already-extracted DB fields (headings, FAQ headings, detected
    product names, table counts). Deliberately omits ``visible_text_extract`` so the raw
    page body is not resent into every Claude call. The raw text stays stored on the
    CompetitorPage row for reference.
    """
    summary: list[dict] = []
    for row in competitor_rows[:limit]:
        summary.append(
            {
                "title": row.title,
                "domain": row.domain,
                "page_type": row.page_type,
                "australian_relevance_score": row.australian_relevance_score,
                "h1": row.h1,
                "h2_list": (row.h2_list or [])[:12],
                "h3_list": (row.h3_list or [])[:12],
                "faq_headings": (row.faq_headings or [])[:8],
                "detected_product_names": (row.detected_product_names or [])[:8],
                "word_count_estimate": row.word_count_estimate,
                "tables_count": row.tables_count,
            }
        )
    return summary


def _brief_rules_summary(brief_outline: dict | None) -> dict:
    """Only the downstream facts/rules an editing step needs from the research brief."""
    outline = brief_outline or {}
    return {
        "primary_keyword": outline.get("primary_keyword"),
        "search_intent": outline.get("search_intent"),
        "recommended_article_angle": outline.get("recommended_article_angle"),
        "required_sections": outline.get("required_sections"),
        "original_value_points": outline.get("original_value_points"),
        "faq_questions": outline.get("faq_questions"),
        "internal_link_suggestions": outline.get("internal_link_suggestions"),
        "forbidden_claims": outline.get("forbidden_claims"),
        "tone_rules": outline.get("tone_rules"),
        "product_requirements": outline.get("product_requirements"),
    }


def _serp_intent_blocks_summary(serp_intent: dict | None) -> dict | None:
    """Compact view of the SERP intent classification: blocks + risks, not the full payload."""
    if not serp_intent:
        return None
    return {
        "primary_intent": serp_intent.get("primary_intent"),
        "secondary_intents": serp_intent.get("secondary_intents") or [],
        "required_blocks": serp_intent.get("required_blocks") or [],
        "optional_blocks": serp_intent.get("optional_blocks") or [],
        "risk_flags": serp_intent.get("risk_flags") or [],
    }


def _sanitise_list(value: list | None, *, max_items: int = MAX_PRODUCT_LIST_ITEMS, item_limit: int = MAX_PRODUCT_FIELD_CHARS) -> list:
    if not value:
        return []
    cleaned = []
    for item in value[:max_items]:
        if isinstance(item, dict):
            useful = [
                str(item.get(key)).strip()
                for key in ("retailer", "url", "price_aud", "price", "availability")
                if item.get(key)
            ]
            text = _truncate_text(" | ".join(useful), item_limit)
        else:
            text = _truncate_text(str(item).strip(), item_limit)
        if text:
            cleaned.append(text)
    return cleaned


def _compact_specs(value) -> dict | list:
    if isinstance(value, list):
        compact = []
        for item in value[:MAX_PRODUCT_SPEC_ITEMS]:
            if isinstance(item, dict):
                compact.append({
                    str(key)[:80]: _truncate_text(str(val), 180)
                    for key, val in list(item.items())[:4]
                    if val not in (None, "")
                })
            else:
                text = _truncate_text(str(item), 180)
                if text:
                    compact.append(text)
        return compact
    if isinstance(value, dict):
        compact = {}
        for key, val in list(value.items())[:MAX_PRODUCT_SPEC_ITEMS]:
            if val in (None, ""):
                continue
            compact[str(key)[:80]] = _truncate_text(str(val), 180)
        return compact
    return {}


def _article_body_system_prompt(base_prompt: str, *, stage: str) -> str:
    return (
        base_prompt
        + "\n\n## Output override for this call\n"
        + f"You are running the {stage} article-body pass.\n"
        + "Return ONLY the complete article body that belongs in `draft_markdown`.\n"
        + "Do not return JSON. Do not include notes, title options, markdown fences, or commentary.\n"
        + "If the post type requires HTML, return the clean HTML article body only.\n"
        + "If the post type requires Markdown, return the Markdown article body only.\n"
    )


def _article_body_from_text(text: str) -> str:
    body = str(text or "").strip()
    if body.startswith("```"):
        body = body.strip("`")
        body = body.split("\n", 1)[1] if "\n" in body else body
    stripped = body.strip()
    if stripped.startswith("{") and '"draft_markdown"' in stripped:
        try:
            payload = json.loads(stripped)
            extracted = payload.get("draft_markdown")
            if isinstance(extracted, str) and extracted.strip():
                return extracted.strip()
        except json.JSONDecodeError:
            pass
    return body.strip()


def _looks_like_image_url(value: str | None) -> bool:
    text = str(value or "").strip().lower()
    if not text.startswith(("http://", "https://")):
        return False
    if any(ext in text for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")):
        return True
    return any(token in text for token in ("/image", "/images/", "/products/", "cdn", "cloudinary"))


def _extract_image_url_from_value(value) -> str | None:
    if isinstance(value, str):
        return value.strip() if _looks_like_image_url(value) else None
    if isinstance(value, list):
        for item in value:
            candidate = _extract_image_url_from_value(item)
            if candidate:
                return candidate
        return None
    if not isinstance(value, dict):
        return None

    priority_keys = (
        "image_url",
        "primary_image_url",
        "featured_image_url",
        "main_image_url",
        "product_image_url",
        "hero_image_url",
        "image",
        "featured_image",
        "main_image",
        "product_image",
        "thumbnail_url",
        "thumbnail",
        "src",
        "url",
    )
    for key in priority_keys:
        if key in value:
            candidate = _extract_image_url_from_value(value.get(key))
            if candidate:
                return candidate

    for key, nested in value.items():
        key_text = str(key).lower()
        if "image" not in key_text and "thumbnail" not in key_text:
            continue
        candidate = _extract_image_url_from_value(nested)
        if candidate:
            return candidate

    for nested in value.values():
        candidate = _extract_image_url_from_value(nested)
        if candidate:
            return candidate
    return None


def _product_image_url(product: Product) -> str:
    for candidate in (
        _extract_image_url_from_value(product.raw_extracted_json),
        _extract_image_url_from_value(product.visible_specs_table),
    ):
        if candidate:
            return candidate
    return NOT_CONFIRMED


def _serialise_product(product: Product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "brand": _sanitise_value(product.brand),
        "category": _sanitise_value(product.category),
        "role": _sanitise_value(product.role),
        "product_url": _sanitise_value(product.product_url),
        "product_image_url": _product_image_url(product),
        "model_number": _sanitise_value(product.model_number),
        "retailer_domain": _sanitise_value(product.retailer_domain),
        "price_text": _sanitise_value(product.price_text),
        "capacity_text": _sanitise_value(product.capacity_text),
        "tank_size_text": _sanitise_value(product.tank_size_text),
        "noise_level_text": _sanitise_value(product.noise_level_text),
        "power_use_text": _sanitise_value(product.power_use_text),
        "warranty_text": _sanitise_value(product.warranty_text),
        "drainage_text": _sanitise_value(product.drainage_text),
        "room_size_text": _sanitise_value(product.room_size_text),
        "review_rating_text": _sanitise_value(product.review_rating_text),
        "review_count_text": _sanitise_value(product.review_count_text),
        "description_snippet": _sanitise_value(product.description_snippet, MAX_PRODUCT_LONG_FIELD_CHARS),
        "visible_specs_table": _compact_specs(product.visible_specs_table),
        "common_positives": _sanitise_value(product.common_positives, MAX_PRODUCT_LONG_FIELD_CHARS),
        "common_complaints": _sanitise_value(product.common_complaints, MAX_PRODUCT_LONG_FIELD_CHARS),
        "who_should_buy": _sanitise_value(product.who_should_buy, MAX_PRODUCT_LONG_FIELD_CHARS),
        "who_should_avoid": _sanitise_value(product.who_should_avoid, MAX_PRODUCT_LONG_FIELD_CHARS),
        "best_for": _sanitise_value(product.best_for, MAX_PRODUCT_LONG_FIELD_CHARS),
        "bottom_line": _sanitise_value(product.bottom_line, MAX_PRODUCT_LONG_FIELD_CHARS),
        "personally_tested": bool(product.personally_tested),
        "confidence_level": _sanitise_value(product.confidence_level),
        "confidence_score": product.confidence_score,
        # Review-led product analysis layer. Drives review-led product sections
        # without implying hands-on testing (gated by personally_tested above).
        "manufacturer_url": _sanitise_value(product.manufacturer_url),
        "retailer_urls": _sanitise_list(product.retailer_urls, max_items=5, item_limit=260),
        "positive_review_patterns": _sanitise_value(product.positive_review_patterns, MAX_PRODUCT_LONG_FIELD_CHARS),
        "negative_review_patterns": _sanitise_value(product.negative_review_patterns, MAX_PRODUCT_LONG_FIELD_CHARS),
        "reliability_concerns": _sanitise_value(product.reliability_concerns, MAX_PRODUCT_LONG_FIELD_CHARS),
        "key_specs": _compact_specs(product.key_specs),
        "price_range_text": _sanitise_value(product.price_range_text),
        "australian_availability": _sanitise_value(product.australian_availability),
        "review_methodology_notes": _sanitise_value(product.review_methodology_notes, MAX_PRODUCT_LONG_FIELD_CHARS),
        "reddit_feedback": (
            product.raw_extracted_json.get("reddit_feedback", [])
            if isinstance(product.raw_extracted_json, dict)
            else []
        ),
    }


def _latest_reddit_feedback(db: Session, article_job_id: int) -> dict | None:
    log = db.scalar(
        select(AppLog)
        .where(AppLog.article_job_id == article_job_id, AppLog.event_type == "workflow.reddit_feedback.completed")
        .order_by(desc(AppLog.created_at))
    )
    if not log or not isinstance(log.metadata_json, dict):
        return None
    metadata = log.metadata_json
    return {
        "qualified_patterns": metadata.get("qualified_patterns") or [],
        "rejected_patterns": metadata.get("rejected_patterns") or [],
        "research_sources": metadata.get("research_sources") or [],
        "notes": metadata.get("notes"),
        "policy": metadata.get("policy") or {
            "reddit_only_for": "anecdotal owner feedback patterns, not specs/prices/safety/medical claims",
        },
    }


def _build_context(db: Session, job: ArticleJob) -> dict:
    brief = _latest_record(db, ArticleBrief, job.id)
    if not brief or not brief.outline_json:
        raise ArticleDraftingError("Research brief is required before drafting.")

    latest_analysis = _latest_record(db, CompetitorAnalysisReport, job.id)
    keyword_rows = list(
        db.scalars(
            select(KeywordResearch)
            .where(KeywordResearch.article_job_id == job.id)
            .order_by(desc(KeywordResearch.search_volume), desc(KeywordResearch.created_at))
        ).all()
    )
    serp_rows = list(
        db.scalars(
            select(SerpResult)
            .where(SerpResult.article_job_id == job.id)
            .order_by(desc(SerpResult.created_at), SerpResult.position.asc())
        ).all()
    )
    competitor_rows = list(
        db.scalars(
            select(CompetitorPage)
            .where(CompetitorPage.article_job_id == job.id)
            .order_by(desc(CompetitorPage.created_at))
        ).all()
    )
    linked_products = [link.product for link in getattr(job, "article_product_links", []) if link.product]

    analysis_payload = None
    if latest_analysis:
        analysis_payload = {
            "id": latest_analysis.id,
            "dominant_intent": latest_analysis.dominant_intent,
            "dominant_page_types_json": latest_analysis.dominant_page_types_json,
            "common_headings_json": latest_analysis.common_headings_json,
            "common_questions_json": latest_analysis.common_questions_json,
            "repeated_products_json": latest_analysis.repeated_products_json,
            "competitor_gaps_json": latest_analysis.competitor_gaps_json,
            "australian_context_gaps_json": latest_analysis.australian_context_gaps_json,
            "recommended_angle": latest_analysis.recommended_angle,
            "original_value_recommendations_json": latest_analysis.original_value_recommendations_json,
            "suggested_support_articles_json": latest_analysis.suggested_support_articles_json,
            "difficulty_estimate": latest_analysis.difficulty_estimate,
        }

    return {
        "article_job": {
            "id": job.id,
            "title": job.title,
            "primary_keyword": job.primary_keyword,
            "post_type": job.post_type,
            "target_audience": job.target_audience,
            "australian_angle": job.australian_angle,
            "notes": job.notes,
            "review_override": job.review_override,
            "current_qa_score": job.current_qa_score,
        },
        "research_brief": {
            "id": brief.id,
            "version": brief.version,
            "outline_json": _brief_rules_summary(brief.outline_json),
            "brief_markdown_excerpt": _truncate_text(brief.brief_markdown, 1000),
        },
        "serp_intent": brief.serp_intent_json,
        "serp_analysis": analysis_payload,
        "keyword_research": [
            {
                "keyword": row.keyword,
                "intent": row.intent,
                "search_volume": row.search_volume,
                "difficulty": row.difficulty,
                "cpc": row.cpc,
                "competition": row.competition,
                "source": row.source,
                "notes": row.notes,
            }
            for row in keyword_rows[:10]
        ],
        "serp_results": [
            {
                "keyword": row.keyword,
                "position": row.position,
                "title": row.title,
                "url": row.url,
                "domain": row.domain,
                "snippet": row.snippet,
                "result_type": row.result_type,
            }
            for row in serp_rows[:5]
        ],
        # Competitor signal is a compact patterns summary (headings/FAQs/products/tables),
        # NOT raw page body text. The full visible_text_extract stays on the DB row.
        "competitor_pages": _competitor_patterns_summary(competitor_rows, limit=5),
        "reddit_feedback": _latest_reddit_feedback(db, job.id),
        "products": [_serialise_product(product) for product in linked_products[:4]],
        "products_available": bool(linked_products),
        "linked_products_count": len(linked_products),
        "product_policy": {
            "linked_products_required_for_named_recommendations": True,
            "when_products_available_is_false": (
                "Do not name specific product models or brands. "
                "Write the product section as category-level buying guidance only, using Not confirmed for missing facts."
            ),
            "when_products_are_linked": (
                "Use only linked product cards as the source of truth for product names, specs, drawbacks, and recommendations."
            ),
        },
        "content_rules": _content_rule_map(db),
        "post_type_generation_rules": get_post_type_generation_rules(job.post_type),
    }


def _build_intent_classifier_input(db: Session, job: ArticleJob) -> dict:
    """Build a compact input for the SERP intent classifier.

    Unlike _build_context, this does NOT require a research brief, because the
    classifier runs after SERP analysis and (optionally) before the brief is
    finalised. The brief is included only if it already exists.
    """
    brief = _latest_record(db, ArticleBrief, job.id)
    latest_analysis = _latest_record(db, CompetitorAnalysisReport, job.id)
    keyword_rows = list(
        db.scalars(
            select(KeywordResearch)
            .where(KeywordResearch.article_job_id == job.id)
            .order_by(desc(KeywordResearch.search_volume), desc(KeywordResearch.created_at))
        ).all()
    )
    competitor_rows = list(
        db.scalars(
            select(CompetitorPage)
            .where(CompetitorPage.article_job_id == job.id)
            .order_by(desc(CompetitorPage.created_at))
        ).all()
    )

    analysis_payload = None
    if latest_analysis:
        analysis_payload = {
            "dominant_intent": latest_analysis.dominant_intent,
            "dominant_page_types_json": latest_analysis.dominant_page_types_json,
            "common_headings_json": latest_analysis.common_headings_json,
            "common_questions_json": latest_analysis.common_questions_json,
            "competitor_gaps_json": latest_analysis.competitor_gaps_json,
            "australian_context_gaps_json": latest_analysis.australian_context_gaps_json,
            "recommended_angle": latest_analysis.recommended_angle,
            "original_value_recommendations_json": latest_analysis.original_value_recommendations_json,
            "difficulty_estimate": latest_analysis.difficulty_estimate,
        }

    return {
        "article_job": {
            "title": job.title,
            "primary_keyword": job.primary_keyword,
            "post_type": job.post_type,
            "target_audience": job.target_audience,
            "australian_angle": job.australian_angle,
            "notes": job.notes,
        },
        "serp_analysis": analysis_payload,
        "keyword_research": [
            {
                "keyword": row.keyword,
                "intent": row.intent,
                "search_volume": row.search_volume,
            }
            for row in keyword_rows[:10]
        ],
        "competitor_pages": [
            {
                "title": row.title,
                "page_type": row.page_type,
                "h2_list": row.h2_list or [],
                "faq_headings": row.faq_headings or [],
            }
            for row in competitor_rows[:5]
        ],
        "research_brief": (brief.outline_json if brief and brief.outline_json else None),
    }


def classify_serp_intent(db: Session, job: ArticleJob) -> dict:
    """Classify search intent and required structure, store on the latest brief.

    Runs after SERP analysis. The output is stored in ArticleBrief.serp_intent_json
    so drafting and QA can reuse it. This step does not draft the
    article and does not invent facts or sources.
    """
    create_app_log(
        db,
        event_type="workflow.serp_intent.started",
        message="SERP intent classification started.",
        article_job_id=job.id,
        metadata_json={"prompt_file": _prompt_path("serp_intent_classifier_prompt.md"), "provider": "Anthropic"},
    )
    try:
        classifier_input = _build_intent_classifier_input(db, job)
        client = AnthropicClient()
        response = client.generate_json(
            system_prompt=_read_prompt("serp_intent_classifier_prompt.md"),
            user_prompt=json.dumps(classifier_input, indent=2, ensure_ascii=False),
            max_tokens=2000,
        )
        intent_payload = _normalise_serp_intent(response)

        brief = _latest_record(db, ArticleBrief, job.id)
        if brief is None:
            # No brief yet: store on a lightweight placeholder brief so the
            # classification is not lost. The research brief step will overwrite
            # outline_json later but preserve serp_intent_json.
            brief = ArticleBrief(article_job_id=job.id, version=1, serp_intent_json=intent_payload)
            db.add(brief)
        else:
            brief.serp_intent_json = intent_payload
            db.add(brief)
        db.commit()
        db.refresh(brief)

        create_app_log(
            db,
            event_type="workflow.serp_intent.completed",
            message="SERP intent classification completed.",
            article_job_id=job.id,
            metadata_json={
                "brief_id": brief.id,
                "primary_intent": intent_payload.get("primary_intent"),
                "required_blocks": intent_payload.get("required_blocks"),
            },
        )
        return {
            "action": "classify SERP intent",
            "article_job_id": job.id,
            "status": job.status,
            "message": "SERP intent classified and stored on the research brief.",
            "next_step": "Generate research brief",
        }
    except (AnthropicError, ArticleDraftingError) as exc:
        create_app_log(
            db,
            event_type="workflow.serp_intent.failed",
            message=f"SERP intent classification failed: {exc}",
            article_job_id=job.id,
            level="ERROR",
            metadata_json={"prompt_file": _prompt_path("serp_intent_classifier_prompt.md")},
        )
        raise


def _normalise_serp_intent(payload: dict) -> dict:
    """Coerce the classifier response into the expected schema with safe defaults."""
    payload = payload if isinstance(payload, dict) else {}

    def _str_list(value) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    specificity = payload.get("specificity_requirements")
    specificity = specificity if isinstance(specificity, dict) else {}
    product = payload.get("product_relevance")
    product = product if isinstance(product, dict) else {}

    return {
        "primary_intent": str(payload.get("primary_intent") or "informational").strip(),
        "secondary_intents": _str_list(payload.get("secondary_intents")),
        "content_type": str(payload.get("content_type") or "").strip(),
        "reader_problem": str(payload.get("reader_problem") or "").strip(),
        "reader_stage": str(payload.get("reader_stage") or "").strip(),
        "required_blocks": _str_list(payload.get("required_blocks")),
        "optional_blocks": _str_list(payload.get("optional_blocks")),
        "risk_flags": _str_list(payload.get("risk_flags")),
        "specificity_requirements": {
            "numbers_or_thresholds_needed": _str_list(specificity.get("numbers_or_thresholds_needed")),
            "formulas_needed": _str_list(specificity.get("formulas_needed")),
            "tables_needed": _str_list(specificity.get("tables_needed")),
            "examples_needed": _str_list(specificity.get("examples_needed")),
            "warnings_needed": _str_list(specificity.get("warnings_needed")),
            "source_placeholders_needed": _str_list(specificity.get("source_placeholders_needed")),
        },
        "product_relevance": {
            "is_product_relevant": bool(product.get("is_product_relevant", False)),
            "product_categories": _str_list(product.get("product_categories")),
            "when_to_buy": str(product.get("when_to_buy") or "").strip(),
            "when_not_to_buy": str(product.get("when_not_to_buy") or "").strip(),
            "specs_that_matter": _str_list(product.get("specs_that_matter")),
        },
    }


def _save_draft(
    db: Session,
    *,
    job_id: int,
    draft_markdown: str,
    stage: str,
    model_name: str | None,
    prompt_name: str,
    seo_title: str | None = None,
    meta_description: str | None = None,
    slug: str | None = None,
    excerpt: str | None = None,
    source_payload_json: dict | None = None,
) -> ArticleDraft:
    latest_version = db.scalar(select(ArticleDraft.version).where(ArticleDraft.article_job_id == job_id).order_by(desc(ArticleDraft.version)))
    draft = ArticleDraft(
        article_job_id=job_id,
        version=(latest_version or 0) + 1,
        stage=stage,
        draft_markdown=draft_markdown,
        seo_title=seo_title,
        meta_description=meta_description,
        slug=slug,
        excerpt=excerpt,
        model_name=model_name,
        prompt_name=prompt_name,
        source_payload_json=source_payload_json,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def _draft_payload_from_response(payload: dict) -> DraftPayload:
    return DraftPayload(
        draft_markdown=payload.get("draft_markdown") or payload.get("draft") or "",
        seo_title=payload.get("seo_title"),
        meta_description=payload.get("meta_description"),
        slug=payload.get("slug"),
        excerpt=payload.get("excerpt"),
        notes=payload.get("notes") or [],
        title_options=payload.get("title_options") or [],
        content_modules=_normalise_content_modules(payload.get("content_modules")),
    )


def _response_model_name(response) -> str | None:
    if isinstance(response, dict):
        model = response.get("model")
        return str(model) if model else None
    model = getattr(response, "model", None)
    return str(model) if model else None


def _content_modules_for_save(job: ArticleJob, payload: DraftPayload, draft_markdown: str) -> list[dict]:
    explicit = payload.content_modules or []
    if explicit:
        return explicit
    return _infer_content_modules(draft_markdown, job.post_type)


def generate_draft(db: Session, job: ArticleJob) -> dict:
    create_app_log(
        db,
        event_type="workflow.generate_draft.started",
        message="Draft generation started.",
        article_job_id=job.id,
        metadata_json={"prompt_file": _prompt_path("article_draft_prompt.md"), "provider": "Anthropic"},
    )
    try:
        context = _build_context(db, job)
        client = AnthropicClient()
        response = client.generate_text(
            system_prompt=_article_body_system_prompt(_read_prompt("article_draft_prompt.md"), stage="first draft"),
            user_prompt=json.dumps(context, indent=2, ensure_ascii=False),
            max_tokens=_draft_max_output_tokens(job),
        )
        payload = DraftPayload(draft_markdown=_article_body_from_text(response.content_text), notes=[], title_options=[], content_modules=[])
        if not payload.draft_markdown.strip():
            raise ArticleDraftingError("Draft response did not include draft_markdown.")
        _assert_ai_output_complete(client, markdown=payload.draft_markdown, stage="Draft generation")
        try:
            draft_markdown = _finalise_draft_markdown(db, job, context, payload.draft_markdown, stage="first_draft")
        except ArticleDraftingError:
            content_modules = _content_modules_for_save(job, payload, payload.draft_markdown)
            _save_draft(
                db,
                job_id=job.id,
                draft_markdown=payload.draft_markdown,
                stage="first_draft",
                model_name=getattr(client, "last_model", None) or _response_model_name(response),
                prompt_name="article_draft_prompt.md",
                source_payload_json={
                    "notes": payload.notes,
                    "title_options": payload.title_options,
                    "content_modules": content_modules,
                    "context_keys": list(context.keys()),
                    "incomplete": True,
                },
            )
            raise
        content_modules = _content_modules_for_save(job, payload, draft_markdown)
        draft = _save_draft(
            db,
            job_id=job.id,
            draft_markdown=draft_markdown,
            stage="first_draft",
            model_name=getattr(client, "last_model", None) or _response_model_name(response),
            prompt_name="article_draft_prompt.md",
            source_payload_json={
                "notes": payload.notes,
                "title_options": payload.title_options,
                "content_modules": content_modules,
                "context_keys": list(context.keys()),
            },
        )
        job.status = ArticleJobStatus.DRAFT_COMPLETE.value
        db.add(job)
        db.commit()
        create_app_log(
            db,
            event_type="workflow.generate_draft.completed",
            message="Draft generation completed.",
            article_job_id=job.id,
            metadata_json={"draft_id": draft.id, **client.usage_metadata()},
        )
        return {
            "action": "generate draft",
            "article_job_id": job.id,
            "status": job.status,
            "message": "Draft generated and saved.",
            "next_step": "Run human edit",
        }
    except (AnthropicError, ArticleDraftingError) as exc:
        create_app_log(
            db,
            event_type="workflow.generate_draft.failed",
            message=f"Draft generation failed: {exc}",
            article_job_id=job.id,
            level="ERROR",
            metadata_json={"prompt_file": _prompt_path("article_draft_prompt.md")},
        )
        raise


def run_human_edit(db: Session, job: ArticleJob) -> dict:
    create_app_log(
        db,
        event_type="workflow.human_edit.started",
        message="Australian human edit started.",
        article_job_id=job.id,
        metadata_json={"prompt_file": _prompt_path("australian_human_edit_prompt.md"), "provider": "Anthropic"},
    )
    try:
        context = _build_context(db, job)
        source_draft = db.scalar(
            select(ArticleDraft)
            .where(ArticleDraft.article_job_id == job.id)
            .order_by(desc(ArticleDraft.created_at))
        )
        if not source_draft or not source_draft.draft_markdown:
            raise ArticleDraftingError("Draft generation is required before the human edit pass.")
        client = AnthropicClient()
        response = client.generate_text(
            system_prompt=_article_body_system_prompt(_read_prompt("australian_human_edit_prompt.md"), stage="Australian human polish"),
            user_prompt=json.dumps(
                _build_edit_input(context, source_draft.draft_markdown),
                indent=2,
                ensure_ascii=False,
            ),
            max_tokens=_draft_max_output_tokens(job),
        )
        payload = DraftPayload(draft_markdown=_article_body_from_text(response.content_text), notes=[], title_options=[], content_modules=[])
        if not payload.draft_markdown.strip():
            raise ArticleDraftingError("Human edit response did not include draft_markdown.")
        _assert_ai_output_complete(client, markdown=payload.draft_markdown, stage="Australian human polish")
        try:
            draft_markdown = _finalise_draft_markdown(db, job, context, payload.draft_markdown, stage="human_edit")
        except ArticleDraftingError:
            content_modules = _content_modules_for_save(job, payload, payload.draft_markdown)
            _save_draft(
                db,
                job_id=job.id,
                draft_markdown=payload.draft_markdown,
                stage="human_edit",
                model_name=getattr(client, "last_model", None) or _response_model_name(response),
                prompt_name="australian_human_edit_prompt.md",
                source_payload_json={"notes": payload.notes, "content_modules": content_modules, "source_draft_id": source_draft.id, "incomplete": True},
            )
            raise
        content_modules = _content_modules_for_save(job, payload, draft_markdown)
        draft = _save_draft(
            db,
            job_id=job.id,
            draft_markdown=draft_markdown,
            stage="human_edit",
            model_name=getattr(client, "last_model", None) or _response_model_name(response),
            prompt_name="australian_human_edit_prompt.md",
            source_payload_json={"notes": payload.notes, "content_modules": content_modules, "source_draft_id": source_draft.id},
        )
        job.status = ArticleJobStatus.DRAFT_COMPLETE.value
        db.add(job)
        db.commit()
        create_app_log(
            db,
            event_type="workflow.human_edit.completed",
            message="Australian human edit completed.",
            article_job_id=job.id,
            metadata_json={"draft_id": draft.id, **client.usage_metadata()},
        )
        return {
            "action": "run human edit",
            "article_job_id": job.id,
            "status": job.status,
            "message": "Australian human edit saved.",
            "next_step": "Run QA",
        }
    except (AnthropicError, ArticleDraftingError) as exc:
        create_app_log(
            db,
            event_type="workflow.human_edit.failed",
            message=f"Australian human edit failed: {exc}",
            article_job_id=job.id,
            level="ERROR",
            metadata_json={"prompt_file": _prompt_path("australian_human_edit_prompt.md")},
        )
        raise


def _build_edit_input(context: dict, draft_markdown: str) -> dict:
    """Compact input for the Australian human edit.

    The edit pass rewrites the existing draft for Australian English, clarity and
    tone. It does NOT need raw competitor pages, raw SERP results, or keyword
    research - those shaped the first draft already. It keeps the hard rules,
    brief facts, product source-of-truth, and the draft itself.
    """
    brief_outline = context["research_brief"]["outline_json"] or {}
    return {
        "article_context": {
            "title": context["article_job"]["title"],
            "primary_keyword": context["article_job"]["primary_keyword"],
            "post_type": context["article_job"]["post_type"],
            "target_audience": context["article_job"]["target_audience"],
            "australian_angle": context["article_job"]["australian_angle"],
        },
        "research_brief": _brief_rules_summary(brief_outline),
        "serp_intent": _serp_intent_blocks_summary(context.get("serp_intent")),
        "products": context["products"],
        "products_available": context["products_available"],
        "product_policy": context["product_policy"],
        "content_rules": context["content_rules"],
        "draft_markdown": draft_markdown,
    }


def _build_fix_input(context: dict, draft_markdown: str, qa_findings: dict | None) -> dict:
    """Compact input for the fix pass.

    The fix pass repairs specific QA-flagged issues in the current draft. It needs
    the draft, the failed checks / fix instructions, the hard rules, brief facts and
    product source-of-truth - but not the raw competitor/SERP/keyword research that
    informed the original draft.
    """
    brief_outline = context["research_brief"]["outline_json"] or {}
    findings = qa_findings if isinstance(qa_findings, dict) else {}
    qa_summary = {
        "failed_checks": findings.get("failed_checks") or [],
        "warnings": findings.get("warnings") or [],
        "fix_instructions": findings.get("fix_instructions") or [],
        "required_blocks_checked": findings.get("required_blocks_checked") or [],
        "optional_blocks_checked": findings.get("optional_blocks_checked") or [],
        "summary": findings.get("summary"),
    }
    return {
        "article_context": {
            "title": context["article_job"]["title"],
            "primary_keyword": context["article_job"]["primary_keyword"],
            "post_type": context["article_job"]["post_type"],
            "target_audience": context["article_job"]["target_audience"],
            "australian_angle": context["article_job"]["australian_angle"],
        },
        "research_brief": _brief_rules_summary(brief_outline),
        "serp_intent": _serp_intent_blocks_summary(context.get("serp_intent")),
        "products": context["products"],
        "products_available": context["products_available"],
        "product_policy": context["product_policy"],
        "content_rules": context["content_rules"],
        "draft_markdown": draft_markdown,
        "qa_findings": qa_summary,
        "fix_instructions": qa_summary["fix_instructions"],
    }


def _build_repair_input(context: dict, current_markdown: str, *, stage: str) -> dict:
    """Compact input for the draft tail repair.

    Repair only writes the missing FAQ + final recommendation tail, so it needs the
    structural rules, brief facts and product source-of-truth - not the full research
    context.
    """
    brief_outline = context["research_brief"]["outline_json"] or {}
    return {
        "article_context": {
            "title": context["article_job"]["title"],
            "primary_keyword": context["article_job"]["primary_keyword"],
            "post_type": context["article_job"]["post_type"],
            "target_audience": context["article_job"]["target_audience"],
            "australian_angle": context["article_job"]["australian_angle"],
        },
        "research_brief": _brief_rules_summary(brief_outline),
        "serp_intent": _serp_intent_blocks_summary(context.get("serp_intent")),
        "products": context["products"],
        "products_available": context["products_available"],
        "product_policy": context["product_policy"],
        "content_rules": context["content_rules"],
        "current_draft_markdown": current_markdown,
        "required_tail_sections": _required_tail_section_markers(context["article_job"]["post_type"]),
        "stage": stage,
    }





def _build_qa_input(db: Session, job: ArticleJob, draft: ArticleDraft, context: dict, *, stage: str) -> dict:
    product_payload = context["products"]
    brief_outline = context["research_brief"]["outline_json"] or {}
    compact_context = {
        "article_job": {
            "title": context["article_job"]["title"],
            "primary_keyword": context["article_job"]["primary_keyword"],
            "post_type": context["article_job"]["post_type"],
            "target_audience": context["article_job"]["target_audience"],
            "australian_angle": context["article_job"]["australian_angle"],
        },
        "research_brief": {
            "primary_keyword": brief_outline.get("primary_keyword"),
            "search_intent": brief_outline.get("search_intent"),
            "recommended_article_angle": brief_outline.get("recommended_article_angle"),
            "required_sections": brief_outline.get("required_sections"),
            "forbidden_claims": brief_outline.get("forbidden_claims"),
            "tone_rules": brief_outline.get("tone_rules"),
            "product_requirements": brief_outline.get("product_requirements"),
            "suggested_title_options": brief_outline.get("suggested_title_options"),
            "suggested_slug": brief_outline.get("suggested_slug"),
            "meta_description_draft": brief_outline.get("meta_description_draft"),
        },
        # products + product_policy are provided once at the top level of the QA input
        # (see return below) so they are not duplicated inside article_context here.
        "content_rules": {
            key: context["content_rules"].get(key)
            for key in [
                "forbidden_phrases",
                "preferred_phrases",
                "australian_spelling_rules",
                "article_templates",
                "product_section_template",
                "qa_scoring_rules",
                "brand_tone_rules",
            ]
            if context["content_rules"].get(key)
        },
    }
    serp_intent_full = context.get("serp_intent") or {}
    serp_intent_summary = {
        "primary_intent": serp_intent_full.get("primary_intent"),
        "secondary_intents": serp_intent_full.get("secondary_intents") or [],
        "required_blocks": serp_intent_full.get("required_blocks") or [],
        "optional_blocks": serp_intent_full.get("optional_blocks") or [],
        "risk_flags": serp_intent_full.get("risk_flags") or [],
    } if serp_intent_full else None
    return {
        "stage": stage,
        "qa_policy": {
            "mode": "draft_generation",
            "internal_links": {
                "missing_links_are_warning_only": True,
                "missing_links_warning": INTERNAL_LINK_DRAFT_WARNING,
                "broken_placeholder_links_can_fail_only_if_publish_ready": True,
            },
            "required_blocks": {
                "missing_required_block_can_fail": True,
                "missing_optional_block_is_warning_only": True,
            },
        },
        "serp_intent": serp_intent_summary,
        "article_context": compact_context,
        "draft_markdown": draft.draft_markdown,
        "product_policy": context["product_policy"],
        "products": product_payload,
        "products_available": context["products_available"],
        # content_rules is intentionally NOT repeated here: the QA-relevant subset
        # (forbidden/preferred phrases, AU spelling, scoring + tone rules) is already
        # included inside article_context.content_rules above. Sending the full map
        # again only duplicated tokens.
    }


def _extract_issue_text(item) -> str:
    if isinstance(item, dict):
        return str(item.get("issue") or item.get("message") or item.get("check") or "").strip()
    return str(item or "").strip()


def _extract_check_name(item) -> str:
    if isinstance(item, dict):
        return str(item.get("check") or "").strip().lower()
    return ""


def _is_internal_link_failure(item) -> bool:
    check_name = _extract_check_name(item)
    issue_text = _extract_issue_text(item).lower()
    return check_name == "internal links suggested" or "internal link" in issue_text


def _is_missing_internal_link_issue(item) -> bool:
    issue_text = _extract_issue_text(item).lower()
    missing_patterns = (
        "no internal links",
        "no internal link",
        "missing internal link",
        "missing internal links",
        "no internal link suggestions",
        "no internal links were included",
        "internal links were not included",
        "internal links missing",
    )
    return any(pattern in issue_text for pattern in missing_patterns)


def _warning_matches_internal_link_policy(item) -> bool:
    if isinstance(item, dict):
        return str(item.get("issue") or "").strip() == INTERNAL_LINK_DRAFT_WARNING
    return str(item or "").strip() == INTERNAL_LINK_DRAFT_WARNING


def _normalise_internal_link_findings(
    failed_checks: list,
    warnings: list,
    *,
    threshold: int,
    score: float,
    passed: bool,
) -> tuple[list, list, float, bool]:
    remaining_failed_checks = []
    internal_link_failures_downgraded = False

    for item in failed_checks:
        if _is_internal_link_failure(item) and _is_missing_internal_link_issue(item):
            internal_link_failures_downgraded = True
            continue
        remaining_failed_checks.append(item)

    updated_warnings = list(warnings)
    if internal_link_failures_downgraded and not any(_warning_matches_internal_link_policy(item) for item in updated_warnings):
        updated_warnings.append(
            {
                "severity": "minor",
                "issue": INTERNAL_LINK_DRAFT_WARNING,
            }
        )

    updated_score = score
    updated_passed = passed
    if internal_link_failures_downgraded and not remaining_failed_checks and updated_score < threshold:
        updated_score = float(threshold)
        updated_passed = True

    return remaining_failed_checks, updated_warnings, updated_score, updated_passed


def _build_seo_input(db: Session, job: ArticleJob, draft: ArticleDraft, context: dict) -> dict:
    brief_outline = context["research_brief"]["outline_json"] or {}
    compact_context = {
        "article_job": {
            "title": context["article_job"]["title"],
            "primary_keyword": context["article_job"]["primary_keyword"],
            "post_type": context["article_job"]["post_type"],
            "target_audience": context["article_job"]["target_audience"],
            "australian_angle": context["article_job"]["australian_angle"],
        },
        "research_brief": {
            "primary_keyword": brief_outline.get("primary_keyword"),
            "search_intent": brief_outline.get("search_intent"),
            "recommended_article_angle": brief_outline.get("recommended_article_angle"),
            "suggested_title_options": brief_outline.get("suggested_title_options"),
            "suggested_slug": brief_outline.get("suggested_slug"),
            "meta_description_draft": brief_outline.get("meta_description_draft"),
        },
        "products": context["products"][:3],
    }
    return {
        "article_context": compact_context,
        "draft_markdown": draft.draft_markdown,
    }


def run_qa(db: Session, job: ArticleJob, *, stage: str = "initial") -> dict:
    create_app_log(
        db,
        event_type="workflow.run_qa.started",
        message=f"QA started ({stage}).",
        article_job_id=job.id,
        metadata_json={"prompt_file": _prompt_path("qa_prompt.md"), "provider": "OpenAI", "stage": stage},
    )
    try:
        context = _build_context(db, job)
        draft = db.scalar(
            select(ArticleDraft)
            .where(ArticleDraft.article_job_id == job.id)
            .order_by(desc(ArticleDraft.created_at))
        )
        if not draft or not draft.draft_markdown:
            raise ArticleDraftingError("A draft is required before QA can run.")
        # Never run QA against a corrupted/truncated draft body (e.g. a raw JSON
        # blob from an older truncated run). Fail clearly instead of wasting a QA
        # pass and an inevitable fix/recheck cycle on unusable content.
        if _looks_like_unparsed_json_draft(draft.draft_markdown):
            raise ArticleDraftingError(
                "The latest draft is corrupted or truncated (it is not valid article markdown). "
                "QA was not run. Regenerate the draft before running QA."
            )
        openai_client = OpenAIClient()
        qa_response = openai_client.generate_json(
            instructions=_read_prompt("qa_prompt.md"),
            input_text=json.dumps(_build_qa_input(db, job, draft, context, stage=stage), indent=2, ensure_ascii=False),
            max_output_tokens=6000,
            cache_key="qa",
        )
        qa_usage = openai_client.usage_metadata()
        score = float(qa_response.get("score", 0))
        passed = bool(qa_response.get("passed", score >= get_qa_threshold(db)))
        threshold = get_qa_threshold(db)
        word_count = _count_words(draft.draft_markdown)
        minimum_word_count = MINIMUM_WORD_COUNTS.get(job.post_type)
        word_count_passed = minimum_word_count is None or word_count >= minimum_word_count
        failed_checks = qa_response.get("failed_checks") or []
        warnings = qa_response.get("warnings") or []
        fix_instructions = qa_response.get("fix_instructions") or []
        summary = qa_response.get("summary")
        failed_checks, warnings, score, passed = _normalise_internal_link_findings(
            failed_checks,
            warnings,
            threshold=threshold,
            score=score,
            passed=passed,
        )
        if not word_count_passed and minimum_word_count is not None:
            word_count_message = (
                f"Draft is too short for {job.post_type}. Minimum {minimum_word_count} words required, found {word_count}."
            )
            failed_checks = [*failed_checks, word_count_message]
            fix_instructions = [
                *fix_instructions,
                f"Expand the article to at least {minimum_word_count} words with useful, evidence-backed sections.",
            ]
            warnings = [*warnings, "Article length is below the minimum quality standard."]
            score = min(score, float(threshold - 1))
            passed = False
            summary = f"{summary} {word_count_message}".strip() if summary else word_count_message
        serp_intent_for_qa = context.get("serp_intent") or {}
        findings = {
            "stage": stage,
            "score": score,
            "passed": passed,
            "threshold": threshold,
            "failed_checks": failed_checks,
            "warnings": warnings,
            "fix_instructions": fix_instructions,
            "manual_override_risk": qa_response.get("manual_override_risk"),
            "summary": summary,
            "word_count": word_count,
            "minimum_word_count": minimum_word_count,
            "minimum_word_count_passed": word_count_passed,
            "required_blocks_checked": serp_intent_for_qa.get("required_blocks") or [],
            "optional_blocks_checked": serp_intent_for_qa.get("optional_blocks") or [],
        }
        seo_response = openai_client.generate_json(
            instructions=_read_prompt("seo_metadata_prompt.md"),
            input_text=json.dumps(_build_seo_input(db, job, draft, context), indent=2, ensure_ascii=False),
            max_output_tokens=1000,
            cache_key="seo",
        )
        seo_usage = openai_client.usage_metadata()
        seo_title = seo_response.get("seo_title")
        meta_description = seo_response.get("meta_description")
        slug = seo_response.get("slug")
        excerpt = seo_response.get("excerpt")
        final_body = draft.draft_markdown or ""
        final_payload = {"qa": findings, "seo": seo_response, "source_draft_id": draft.id}
        # Avoid duplicating the full article body into a new draft record when the
        # final stage only attaches SEO metadata. If an identical-body final draft
        # already exists, update its metadata in place instead of versioning again.
        existing_final = db.scalar(
            select(ArticleDraft)
            .where(ArticleDraft.article_job_id == job.id, ArticleDraft.stage == "final")
            .order_by(desc(ArticleDraft.version))
        )
        final_duplication_skipped = bool(
            existing_final is not None and (existing_final.draft_markdown or "") == final_body
        )
        if final_duplication_skipped:
            existing_final.seo_title = seo_title
            existing_final.meta_description = meta_description
            existing_final.slug = slug
            existing_final.excerpt = excerpt
            existing_final.model_name = openai_client.model
            existing_final.prompt_name = "seo_metadata_prompt.md"
            existing_final.source_payload_json = final_payload
            db.add(existing_final)
            db.commit()
            db.refresh(existing_final)
            final_draft = existing_final
            create_app_log(
                db,
                event_type="workflow.run_qa.final_dedup",
                message="No content change; draft version not duplicated.",
                article_job_id=job.id,
                metadata_json={"final_draft_id": final_draft.id, "stage": stage},
            )
        else:
            final_draft = _save_draft(
                db,
                job_id=job.id,
                draft_markdown=final_body,
                stage="final",
                model_name=openai_client.model,
                prompt_name="seo_metadata_prompt.md",
                seo_title=seo_title,
                meta_description=meta_description,
                slug=slug,
                excerpt=excerpt,
                source_payload_json=final_payload,
            )
        report = QaReport(
            article_job_id=job.id,
            status="pass" if (score >= threshold or job.review_override) else "needs_revision",
            score=score,
            passed_gate=bool(score >= threshold or job.review_override),
            findings_json={**findings, "seo_metadata": seo_response},
            summary=summary,
            model_name=openai_client.model,
            prompt_name="qa_prompt.md",
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        job.current_qa_score = score
        job.status = ArticleJobStatus.READY_FOR_REVIEW.value if (score >= threshold or job.review_override) else ArticleJobStatus.QA_FAILED.value
        db.add(job)
        db.commit()
        create_app_log(
            db,
            event_type="workflow.run_qa.completed",
            message="QA completed.",
            article_job_id=job.id,
            metadata_json={
                "score": score,
                "threshold": threshold,
                "passed": score >= threshold or job.review_override,
                "qa_report_id": report.id,
                "final_draft_id": final_draft.id,
                "stage": stage,
                "final_duplication_skipped": final_duplication_skipped,
                "qa_usage": qa_usage,
                "seo_usage": seo_usage,
            },
        )
        return {
            "action": "run QA",
            "article_job_id": job.id,
            "status": job.status,
            "message": (
                "QA passed and the final draft is ready for review."
                if score >= threshold or job.review_override
                else "QA completed. The draft needs a fix pass before it can be marked ready for review."
            ),
            "next_step": "Export to WordPress draft" if (score >= threshold or job.review_override) else "Run fix pass",
        }
    except (OpenAIError, ArticleDraftingError) as exc:
        create_app_log(
            db,
            event_type="workflow.run_qa.failed",
            message=f"QA failed: {exc}",
            article_job_id=job.id,
            level="ERROR",
            metadata_json={"prompt_file": _prompt_path("qa_prompt.md"), "stage": stage},
        )
        raise


def run_fix_pass(db: Session, job: ArticleJob) -> dict:
    create_app_log(
        db,
        event_type="workflow.fix_pass.started",
        message="Fix pass started.",
        article_job_id=job.id,
        metadata_json={"prompt_file": _prompt_path("australian_human_edit_prompt.md"), "provider": "Anthropic"},
    )
    try:
        context = _build_context(db, job)
        latest_qa = db.scalar(
            select(QaReport)
            .where(QaReport.article_job_id == job.id)
            .order_by(desc(QaReport.created_at))
        )
        draft = db.scalar(
            select(ArticleDraft)
            .where(ArticleDraft.article_job_id == job.id)
            .order_by(desc(ArticleDraft.created_at))
        )
        if not draft or not draft.draft_markdown:
            raise ArticleDraftingError("A draft is required before a fix pass can run.")
        if not latest_qa or not latest_qa.findings_json:
            raise ArticleDraftingError("A QA report is required before a fix pass can run.")
        client = AnthropicClient()
        response = client.generate_text(
            system_prompt=_article_body_system_prompt(_read_prompt("australian_human_edit_prompt.md"), stage="fix pass"),
            user_prompt=json.dumps(
                _build_fix_input(context, draft.draft_markdown, latest_qa.findings_json),
                indent=2,
                ensure_ascii=False,
            ),
            max_tokens=_draft_max_output_tokens(job),
        )
        payload = DraftPayload(draft_markdown=_article_body_from_text(response.content_text), notes=[], title_options=[], content_modules=[])
        if not payload.draft_markdown.strip():
            raise ArticleDraftingError("Fix pass response did not include draft_markdown.")
        _assert_ai_output_complete(client, markdown=payload.draft_markdown, stage="Fix pass")
        draft_markdown = _finalise_draft_markdown(db, job, context, payload.draft_markdown, stage="fix_pass")
        content_modules = _content_modules_for_save(job, payload, draft_markdown)
        revised = _save_draft(
            db,
            job_id=job.id,
            draft_markdown=draft_markdown,
            stage="fix_pass",
            model_name=getattr(client, "last_model", None) or _response_model_name(response),
            prompt_name="australian_human_edit_prompt.md",
            source_payload_json={"notes": payload.notes, "content_modules": content_modules, "qa_report_id": latest_qa.id, "source_draft_id": draft.id},
        )
        job.status = ArticleJobStatus.DRAFT_COMPLETE.value
        db.add(job)
        db.commit()
        create_app_log(
            db,
            event_type="workflow.fix_pass.completed",
            message="Fix pass completed.",
            article_job_id=job.id,
            metadata_json={"draft_id": revised.id, "qa_report_id": latest_qa.id, **client.usage_metadata()},
        )
        return {
            "action": "run fix pass",
            "article_job_id": job.id,
            "status": job.status,
            "message": "Fix pass saved. Run QA again to confirm the score.",
            "next_step": "Run QA",
        }
    except (AnthropicError, ArticleDraftingError) as exc:
        create_app_log(
            db,
            event_type="workflow.fix_pass.failed",
            message=f"Fix pass failed: {exc}",
            article_job_id=job.id,
            level="ERROR",
            metadata_json={"prompt_file": _prompt_path("australian_human_edit_prompt.md")},
        )
        raise


def list_article_drafts(db: Session, job_id: int) -> list[ArticleDraft]:
    return list(
        db.scalars(
            select(ArticleDraft)
            .where(ArticleDraft.article_job_id == job_id)
            .order_by(desc(ArticleDraft.created_at))
        ).all()
    )


def list_qa_reports(db: Session, job_id: int) -> list[QaReport]:
    return list(
        db.scalars(
            select(QaReport)
            .where(QaReport.article_job_id == job_id)
            .order_by(desc(QaReport.created_at))
        ).all()
    )
