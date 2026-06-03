"""Parse a free-text keyword blob into a clean, de-duplicated list of keywords.

Used by the Bulk Standard Posts queue. The parser:
- splits on newlines AND commas
- trims surrounding whitespace
- removes blank entries
- de-duplicates exact matches (case-insensitive), preserving the first occurrence
  and its original wording
"""

from __future__ import annotations

import re


def slugify(value: str) -> str:
    """Build the same slug shape used by ArticleJob.local_export_path."""
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug


def parse_keywords(raw: str) -> list[str]:
    """Return a clean, de-duplicated, order-preserving list of keywords.

    Splits on newlines and commas, trims whitespace, drops blanks, and removes
    exact (case-insensitive) duplicates while keeping the original wording of the
    first occurrence.
    """
    if not raw:
        return []

    # Split on newlines and commas in one pass.
    tokens = re.split(r"[\n,]+", raw)

    seen: set[str] = set()
    keywords: list[str] = []
    for token in tokens:
        keyword = token.strip()
        if not keyword:
            continue
        key = keyword.casefold()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(keyword)
    return keywords
