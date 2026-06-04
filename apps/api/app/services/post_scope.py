from __future__ import annotations

import re

from app.models.entities import ArticleJob, PostType


BASE_POST_TYPE_MIN_PRODUCTS: dict[str, int] = {
    PostType.INFORMATIONAL_BLOG.value: 0,
    PostType.MONEY_POST.value: 3,
    PostType.SINGLE_PRODUCT_REVIEW.value: 1,
    PostType.PRODUCT_COMPARISON.value: 2,
    PostType.BEST_X_FOR_Y.value: 3,
}


def _normalise(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def commercial_page_scope(post_type: str, keyword: str | None, title: str | None = None) -> str:
    """Classify commercial article breadth for product-depth and QA rules."""
    text = _normalise(keyword) or _normalise(title)
    if post_type not in {PostType.MONEY_POST.value, PostType.BEST_X_FOR_Y.value}:
        return "not_commercial_money_page"

    if post_type == PostType.BEST_X_FOR_Y.value:
        return "use_case_money_page"

    if not text:
        return "standard_money_page"

    broad_best_pattern = re.match(r"^best\s+[\w\s-]+\s+australia(?:\s+\d{4})?$", text)
    narrow_modifiers = (
        " for ",
        "bedroom",
        "bathroom",
        "mould",
        "mold",
        "condensation",
        "laundry",
        "drying clothes",
        "small room",
        "large room",
        "apartment",
        "rental",
        "quiet",
        "budget",
        "cheap",
        "premium",
    )
    if broad_best_pattern and not any(modifier in text for modifier in narrow_modifiers):
        return "broad_category_money_page"
    return "standard_money_page"


def get_min_products_for_post_type(post_type: str) -> int:
    return BASE_POST_TYPE_MIN_PRODUCTS.get(post_type, 0)


def get_min_products_for_article(job: ArticleJob) -> int:
    scope = commercial_page_scope(job.post_type, job.primary_keyword, job.title)
    if scope == "broad_category_money_page":
        return 8
    if scope == "use_case_money_page":
        return 5
    return get_min_products_for_post_type(job.post_type)


def get_max_products_for_article(job: ArticleJob) -> int:
    scope = commercial_page_scope(job.post_type, job.primary_keyword, job.title)
    if scope == "broad_category_money_page":
        return 10
    if scope == "use_case_money_page":
        return 7
    if job.post_type == PostType.MONEY_POST.value:
        return 6
    return max(get_min_products_for_article(job), 5)
