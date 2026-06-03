"""Legacy article_type → post_type compatibility helpers.

Old DB rows and Completed-Articles JSON exports stored human-readable strings
like "Buying guide".  This module provides a canonical map and a resolver so
any code reading a stored value can normalise it to the snake_case PostType
values without needing to touch the exported files.
"""

from __future__ import annotations

_LEGACY_TYPE_MAP: dict[str, str] = {
    "Money page": "money_post",
    "Buying guide": "money_post",
    "Problem-solving post": "informational_blog",
    "Comparison post": "product_comparison",
    "Informational support post": "informational_blog",
    "Product review-style page": "single_product_review",
}


def resolve_post_type(value_or_payload: str | dict) -> str:
    """Return a normalised PostType value from a raw string or a dict payload.

    When given a dict, prefers the ``post_type`` key and falls back to the
    legacy ``article_type`` key.  Legacy display strings (e.g. "Buying guide")
    are mapped to their snake_case equivalents.  Unknown values are returned
    as-is so callers can surface validation errors if needed.
    """
    if isinstance(value_or_payload, dict):
        raw = value_or_payload.get("post_type") or value_or_payload.get("article_type") or ""
    else:
        raw = value_or_payload or ""
    return _LEGACY_TYPE_MAP.get(raw, raw)
