from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.entities import ArticleDraft, ArticleJob, PostType
REPO_ROOT = Path(__file__).resolve().parents[4]
RENDERER_PATH = REPO_ROOT / "scripts" / "article-html-renderer.js"


@dataclass(slots=True)
class HtmlValidationCheck:
    key: str
    label: str
    passed: bool
    detail: str


@dataclass(slots=True)
class HtmlValidationResult:
    passed: bool
    summary: str
    checks: list[HtmlValidationCheck]
    html_path: str | None = None


COMMERCIAL_POST_TYPES = {
    PostType.MONEY_POST.value,
    PostType.BEST_X_FOR_Y.value,
    PostType.SINGLE_PRODUCT_REVIEW.value,
    PostType.PRODUCT_COMPARISON.value,
}

TABLE_REQUIRED_POST_TYPES = {
    PostType.MONEY_POST.value,
    PostType.BEST_X_FOR_Y.value,
    PostType.PRODUCT_COMPARISON.value,
}

MIN_PRODUCT_CARDS = {
    PostType.MONEY_POST.value: 3,
    PostType.BEST_X_FOR_Y.value: 3,
    PostType.SINGLE_PRODUCT_REVIEW.value: 1,
    PostType.PRODUCT_COMPARISON.value: 2,
}


def _check(key: str, label: str, passed: bool, detail: str) -> HtmlValidationCheck:
    return HtmlValidationCheck(key=key, label=label, passed=passed, detail=detail)


def _strip_style_blocks(html: str) -> str:
    return re.sub(r"<style\b[\s\S]*?</style>", "", html, flags=re.IGNORECASE)


def _tag_count(html: str, tag: str, *, closing: bool = False) -> int:
    slash = "/" if closing else ""
    return len(re.findall(rf"<{slash}{tag}\b", html, flags=re.IGNORECASE))


def _ids(html: str) -> set[str]:
    return {match.group(2) for match in re.finditer(r"\sid=(['\"])(.*?)\1", html, flags=re.IGNORECASE)}


def _href_anchors(html: str, class_name: str) -> list[str]:
    anchors: list[str] = []
    regex = re.compile(
        rf"<a\b(?=[^>]*class=(['\"])[^'\"]*\b{re.escape(class_name)}\b[^'\"]*\1)[^>]*href=(['\"])#([^'\"]+)\2",
        flags=re.IGNORECASE,
    )
    for match in regex.finditer(html):
        anchors.append(match.group(3))
    return anchors


def _has_table_rows(html: str) -> bool:
    return bool(re.search(r"<table\b[\s\S]*?<tbody\b[\s\S]*?<tr\b", html, flags=re.IGNORECASE))


def _find_html_file(job: ArticleJob, draft: ArticleDraft | None) -> Path | None:
    if not job.local_export_path:
        return None
    root = Path(job.local_export_path)
    if not root.exists():
        return None
    candidates: list[Path] = []
    if draft and draft.slug:
        candidates.append(root / f"{draft.slug}.html")
    candidates.extend(sorted(root.glob("*.html"), key=lambda path: path.stat().st_mtime, reverse=True))
    return next((path for path in candidates if path.exists()), None)


def render_article_html(draft: ArticleDraft, post_type: str, *, wordpress_blocks: bool = False) -> str:
    if not RENDERER_PATH.exists():
        raise RuntimeError(f"Article HTML renderer script not found: {RENDERER_PATH}")

    source_payload = draft.source_payload_json if isinstance(draft.source_payload_json, dict) else {}
    payload = {
        "draft_markdown": draft.draft_markdown or "",
        "post_type": post_type,
        "content_modules": source_payload.get("content_modules") or [],
        "wordpress_blocks": wordpress_blocks,
    }
    runner = """
const fs = require('fs');
const rendererPath = process.argv[1];
let data = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { data += chunk; });
process.stdin.on('end', () => {
  const payload = JSON.parse(data);
  const { renderArticleHtml } = require(rendererPath);
  const html = renderArticleHtml(payload.draft_markdown || '', {
    post_type: payload.post_type || 'informational_blog',
    content_modules: payload.content_modules || [],
    wordpressBlocks: Boolean(payload.wordpress_blocks),
  });
  process.stdout.write(html);
});
"""
    result = subprocess.run(
        ["node", "-e", runner, str(RENDERER_PATH.resolve())],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "Article HTML rendering failed.")
    return result.stdout


def validate_html_structure(html: str, *, post_type: str, expect_wordpress_block: bool = False) -> HtmlValidationResult:
    body = html or ""
    body_without_style = _strip_style_blocks(body)
    checks: list[HtmlValidationCheck] = []

    checks.append(_check("not_empty", "HTML exists", bool(body.strip()), "Rendered HTML is present." if body.strip() else "Rendered HTML is empty."))
    checks.append(_check(
        "article_container",
        "Article container",
        'class="hdl-article-content"' in body,
        "Scoped Home Dry Lab article container is present." if 'class="hdl-article-content"' in body else "Missing .hdl-article-content wrapper.",
    ))
    checks.append(_check(
        "wordpress_block",
        "Gutenberg HTML block",
        (not expect_wordpress_block) or bool(re.search(r"^\s*<!--\s+wp:html\s+-->", body) and re.search(r"<!--\s+/wp:html\s+-->\s*$", body)),
        "WordPress HTML block wrapper is present." if expect_wordpress_block else "WordPress block wrapper not required for local preview.",
    ))
    checks.append(_check(
        "forbidden_tags",
        "No forbidden document/script tags",
        not re.search(r"<(?:html|head|body|script)\b", body_without_style, flags=re.IGNORECASE),
        "No html/head/body/script tags found." if not re.search(r"<(?:html|head|body|script)\b", body_without_style, flags=re.IGNORECASE) else "Found html/head/body/script tags in article content.",
    ))
    checks.append(_check(
        "no_inline_styles",
        "No inline styles",
        not re.search(r"\sstyle=(['\"])", body_without_style, flags=re.IGNORECASE),
        "No inline style attributes found." if not re.search(r"\sstyle=(['\"])", body_without_style, flags=re.IGNORECASE) else "Inline style attributes found.",
    ))
    checks.append(_check(
        "no_raw_markdown",
        "No raw markdown leaked",
        not re.search(r"(^|\n)\s{0,3}#{1,6}\s+\S|\*\*[^*]+\*\*|```", body_without_style),
        "No markdown syntax leaked into rendered HTML." if not re.search(r"(^|\n)\s{0,3}#{1,6}\s+\S|\*\*[^*]+\*\*|```", body_without_style) else "Raw markdown syntax appears in rendered HTML.",
    ))
    checks.append(_check(
        "no_malformed_wrappers",
        "No malformed wrappers",
        not re.search(r"<p>\s*<(?:article|section|div|table|nav|figure)\b", body, flags=re.IGNORECASE),
        "No block elements are incorrectly wrapped in paragraphs." if not re.search(r"<p>\s*<(?:article|section|div|table|nav|figure)\b", body, flags=re.IGNORECASE) else "Block-level HTML appears inside a paragraph tag.",
    ))

    for tag in ("article", "section", "div", "nav", "figure", "table"):
        opens = _tag_count(body_without_style, tag)
        closes = _tag_count(body_without_style, tag, closing=True)
        checks.append(_check(
            f"balanced_{tag}",
            f"Balanced <{tag}> tags",
            opens == closes,
            f"{opens} opening and {closes} closing <{tag}> tags.",
        ))

    has_faq_heading = bool(re.search(r"faq|frequently asked questions", body, flags=re.IGNORECASE))
    faq_accordion_present = 'class="hdl-faq-section"' in body and 'class="hdl-faq-accordion"' in body
    checks.append(_check(
        "faq_accordion",
        "FAQ accordion",
        (not has_faq_heading) or faq_accordion_present,
        "FAQ is rendered as an accordion." if faq_accordion_present else (
            "FAQ section detected, but the accordion wrapper is missing." if has_faq_heading else "No FAQ section detected."
        ),
    ))

    if post_type in COMMERCIAL_POST_TYPES:
        card_count = len(re.findall(r"class=(['\"])[^'\"]*(?:product-card featured|hdl-product-review-card|product-review)[^'\"]*\1", body, flags=re.IGNORECASE))
        min_cards = max(1, min(3, MIN_PRODUCT_CARDS.get(post_type, 1)))
        checks.append(_check(
            "product_cards",
            "Product cards/reviews",
            card_count >= min_cards,
            f"Found {card_count} product card/review block(s); expected at least {min_cards}.",
        ))

    if post_type in TABLE_REQUIRED_POST_TYPES:
        checks.append(_check(
            "comparison_table",
            "Comparison table",
            'class="hdl-table"' in body and _has_table_rows(body),
            "Comparison table with body rows is present." if 'class="hdl-table"' in body and _has_table_rows(body) else "Missing comparison table or table rows.",
        ))

    review_targets = _href_anchors(body, "read-review-link")
    if review_targets:
        ids = _ids(body)
        missing = [target for target in review_targets if target not in ids]
        checks.append(_check(
            "review_anchor_targets",
            "Read-review anchors",
            not missing,
            "All Read review links target an existing review block." if not missing else f"Missing review target id(s): {', '.join(missing[:5])}.",
        ))

    passed = all(check.passed for check in checks)
    failed_count = len([check for check in checks if not check.passed])
    summary = "HTML structure passed." if passed else f"HTML structure has {failed_count} issue(s)."
    return HtmlValidationResult(passed=passed, summary=summary, checks=checks)


def validate_latest_article_html(db: Session, job: ArticleJob, *, wordpress_blocks: bool = False) -> HtmlValidationResult:
    draft = db.scalar(
        select(ArticleDraft)
        .where(ArticleDraft.article_job_id == job.id)
        .order_by(desc(ArticleDraft.created_at))
    )
    if not draft or not draft.draft_markdown:
        return HtmlValidationResult(
            passed=False,
            summary="No draft is available to render.",
            checks=[_check("draft_exists", "Draft exists", False, "Generate a draft before HTML validation.")],
        )
    html = render_article_html(draft, job.post_type, wordpress_blocks=wordpress_blocks)
    result = validate_html_structure(html, post_type=job.post_type, expect_wordpress_block=wordpress_blocks)
    html_file = _find_html_file(job, draft)
    result.html_path = str(html_file) if html_file else None
    return result


def serialise_html_validation(result: HtmlValidationResult) -> dict:
    return {
        "passed": result.passed,
        "summary": result.summary,
        "html_path": result.html_path,
        "checks": [
            {
                "key": check.key,
                "label": check.label,
                "passed": check.passed,
                "detail": check.detail,
            }
            for check in result.checks
        ],
    }
