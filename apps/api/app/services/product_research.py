from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import ArticleJobProduct, Product
from app.services.competitor_extraction import _fetch_html_http, _fetch_html_playwright

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _read_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


NOT_CONFIRMED = "Not confirmed"
MIN_HTML_LENGTH = 300
PRODUCT_DESCRIPTION_LIMIT = 500
BOT_CHALLENGE_MARKERS = [
    "as you were browsing something about your browser made us think you were a bot",
    "pardon our interruption",
    "verify you are a human",
    "access denied",
    "robot check",
    "captcha",
]
# Markers that indicate the page never delivered real product content because it
# requires JavaScript, blocks scraping, or served an interstitial wall.
BLOCKED_PAGE_MARKERS = [
    "it looks like you have scripts disabled",
    "scripts disabled",
    "enable javascript",
    "javascript is disabled",
    "javascript is required",
    "please enable cookies",
    "cookies are disabled",
    "checking your browser",
    "checking if the site connection is secure",
    "enable js and disable any ad blocker",
    "are you a robot",
    "this site requires javascript",
    "turn on javascript",
]
# Slug tokens that are retailer/marketing noise rather than product identity.
SLUG_NOISE_TOKENS = {
    "buy",
    "shop",
    "online",
    "product",
    "products",
    "p",
    "dp",
    "item",
    "items",
    "sale",
    "best",
    "cheap",
    "au",
    "australia",
    "category",
    "categories",
    "c",
    "ref",
    "review",
    "reviews",
    "the",
    "and",
    "with",
    "for",
}
TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "_ga",
    "_gl",
}


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def _value_or_not_confirmed(value: str | None) -> str:
    return _clean_text(value) or NOT_CONFIRMED


def clean_product_url(url: str) -> str:
    parsed = urlparse(url.strip())
    kept_params = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_PARAMS
    ]
    cleaned = parsed._replace(query=urlencode(kept_params, doseq=True), fragment="")
    return urlunparse(cleaned)


def _first_match(patterns: Iterable[str], text: str, *, flags: int = re.IGNORECASE) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return _clean_text(match.group(1) if match.lastindex else match.group(0))
    return None


def _table_map(soup: BeautifulSoup) -> dict[str, str]:
    specs: dict[str, str] = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            if len(cells) >= 2:
                key = _clean_text(cells[0])
                value = _clean_text(cells[1])
                if key and value:
                    specs[key] = value
    return specs


def _lookup_table_value(specs: dict[str, str], keywords: Iterable[str]) -> str | None:
    for key, value in specs.items():
        lower_key = key.lower()
        if any(keyword in lower_key for keyword in keywords):
            return value
    return None


def _extract_brand(product_name: str, title: str | None, soup: BeautifulSoup) -> str | None:
    site_name = soup.find("meta", attrs={"property": "og:site_name"})
    if site_name and _clean_text(site_name.get("content", "")):
        return _clean_text(site_name.get("content", "")) or None
    if title:
        for separator in (" | ", " - "):
            if separator in title:
                brand = _clean_text(title.split(separator)[-1])
                if brand:
                    return brand
    text = product_name if product_name != NOT_CONFIRMED else _clean_text(title)
    if not text:
        return None
    parts = text.split()
    if len(parts) > 1 and parts[0].lower() not in {"series", "model", "product"}:
        return parts[0]
    return None


def _extract_model(product_name: str, text: str, specs: dict[str, str], url: str) -> str | None:
    table_value = _lookup_table_value(specs, ["model"])
    if table_value:
        cleaned = _clean_text(table_value)
        if cleaned and cleaned.lower() not in {"number", "model number", "part number"}:
            return cleaned
    for path_part in [part for part in urlparse(url).path.split("/") if part]:
        candidate = path_part.replace("_", "/")
        if re.fullmatch(r"[A-Z0-9]+(?:/[A-Z0-9]+)+", candidate):
            return candidate
    match = _first_match(
        [
            r"manufacturer'?s part number(?: for this product)? is ([A-Z0-9\-]+)",
            r"part number(?: is|:)?\s*([A-Z0-9\-]+)",
            r"model(?: number)?(?: is|:)?\s*([A-Z0-9\-]+)",
            r"\b([A-Z0-9]{3,}(?:[- ][A-Z0-9]{2,})+)\b",
        ],
        text,
    )
    if match and match.lower() not in {"number", "model number", "part number"}:
        return match
    match = re.search(r"\b([A-Z0-9]{2,}(?:[- ][A-Z0-9]{2,})+)\b", product_name)
    if match and match.group(1).lower() not in {"number", "model number", "part number"}:
        return match.group(1)
    return None


def _detect_product_name(soup: BeautifulSoup, title: str | None) -> str:
    h1 = soup.find("h1")
    if h1 and _clean_text(h1.get_text(" ", strip=True)):
        return _clean_text(h1.get_text(" ", strip=True)) or NOT_CONFIRMED
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and _clean_text(og_title.get("content", "")):
        return _clean_text(og_title.get("content", "")) or NOT_CONFIRMED
    return _value_or_not_confirmed(title)


def _extract_description(soup: BeautifulSoup, visible_text: str) -> str:
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and _clean_text(meta.get("content", "")):
        return (_clean_text(meta.get("content", "")) or NOT_CONFIRMED)[:PRODUCT_DESCRIPTION_LIMIT]
    first_p = soup.find("p")
    if first_p and _clean_text(first_p.get_text(" ", strip=True)):
        return (_clean_text(first_p.get_text(" ", strip=True)) or NOT_CONFIRMED)[:PRODUCT_DESCRIPTION_LIMIT]
    return _value_or_not_confirmed(visible_text[:PRODUCT_DESCRIPTION_LIMIT] if visible_text else None)


def _looks_like_bot_challenge(text: str, title: str | None) -> bool:
    haystack = f"{title or ''} {text}".lower()
    return any(marker in haystack for marker in BOT_CHALLENGE_MARKERS)


def _looks_like_blocked_page(text: str | None, title: str | None) -> bool:
    """Detect no-JS / script-disabled / interstitial walls that contain no real product content."""
    haystack = f"{title or ''} {text or ''}".lower()
    if any(marker in haystack for marker in BOT_CHALLENGE_MARKERS):
        return True
    return any(marker in haystack for marker in BLOCKED_PAGE_MARKERS)


def detect_blocked_reason(*, html: str | None, visible_text: str | None, title: str | None) -> str | None:
    """Return a short human reason if the fetched page looks blocked/empty, else None."""
    if not html or len(html.strip()) < MIN_HTML_LENGTH:
        return "Page returned too little content to read (likely blocked or requires JavaScript)."
    if _looks_like_bot_challenge(visible_text or html, title):
        return "Page returned an anti-bot challenge instead of product content."
    if _looks_like_blocked_page(visible_text, title):
        return "Page requires JavaScript or blocks scraping (no-script / cookie wall)."
    return None


def _humanise_slug_tokens(tokens: list[str]) -> list[str]:
    cleaned: list[str] = []
    for token in tokens:
        lower = token.lower()
        if lower in SLUG_NOISE_TOKENS:
            continue
        if re.fullmatch(r"\d{4,}", token):  # drop pure numeric retailer ids
            continue
        cleaned.append(token)
    return cleaned


def infer_product_clues_from_url(url: str, title: str | None = None) -> dict:
    """Derive best-effort product identity clues from a URL slug and optional page title.

    Never fabricates specs/prices. Only returns guesses that a human must confirm.
    """
    parsed = urlparse(url)
    retailer = parsed.netloc or None
    path_parts = [part for part in parsed.path.split("/") if part]
    # The product slug is usually the longest hyphenated path segment.
    slug = ""
    for part in path_parts:
        if "-" in part and len(part) > len(slug):
            slug = part
    if not slug and path_parts:
        slug = path_parts[-1]

    raw_tokens = [tok for tok in re.split(r"[-_]+", slug) if tok]
    name_tokens = _humanise_slug_tokens(raw_tokens)

    inferred_model = None
    for tok in raw_tokens:
        # Model numbers look like alphanumeric mixes (e.g. MJ-E16VX, DH40).
        if re.search(r"\d", tok) and re.search(r"[a-zA-Z]", tok) and len(tok) >= 3:
            inferred_model = tok.upper()
            break

    inferred_brand = None
    if name_tokens:
        first = name_tokens[0]
        if first.isalpha() and len(first) > 1:
            inferred_brand = first.capitalize()

    inferred_name = " ".join(part.capitalize() for part in name_tokens) or None
    if not inferred_name and title:
        inferred_name = _clean_text(title)

    category_guess = None
    haystack = f"{slug} {title or ''}".lower()
    for keyword in ("dehumidifier", "air purifier", "humidifier", "heater", "fan", "aircon", "air conditioner"):
        if keyword.replace(" ", "") in haystack.replace(" ", "") or keyword in haystack:
            category_guess = keyword
            break

    return {
        "inferred_name": inferred_name,
        "inferred_brand": inferred_brand,
        "inferred_model": inferred_model,
        "retailer": retailer,
        "category_guess": category_guess,
        "slug_tokens": name_tokens,
    }


def _extract_spec_field(*, specs: dict[str, str], text: str, table_keywords: list[str], patterns: list[str]) -> str:
    table_value = _lookup_table_value(specs, table_keywords)
    if table_value:
        return table_value
    return NOT_CONFIRMED


def calculate_confidence(*, source_types: set[str], key_spec_count: int) -> tuple[str, int]:
    if "manufacturer" in source_types and "retailer" in source_types and key_spec_count >= 4:
        return "High", 90
    if "retailer" in source_types and key_spec_count >= 2:
        return "Medium", 65
    if key_spec_count >= 3:
        return "Medium", 55
    return "Low", 30


def extract_product_data_from_html(url: str, html: str, *, source_type: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = _clean_text(soup.title.get_text(" ", strip=True) if soup.title else None)
    visible_text = _clean_text(soup.get_text(" ", strip=True)) or ""
    if _looks_like_bot_challenge(visible_text, title):
        raise RuntimeError("Product page returned an anti-bot challenge instead of product content.")
    specs_table = _table_map(soup)
    product_name = _detect_product_name(soup, title)
    brand = _value_or_not_confirmed(_extract_brand(product_name, title, soup))
    model_number = _value_or_not_confirmed(_extract_model(product_name, visible_text, specs_table, url))
    price_text = _extract_spec_field(
        specs=specs_table,
        text=visible_text,
        table_keywords=["price", "rrp"],
        patterns=[r"((?:AUD|\$)\s?\d[\d,]*(?:\.\d{2})?)"],
    )
    capacity_text = _extract_spec_field(
        specs=specs_table,
        text=visible_text,
        table_keywords=["capacity", "moisture removal", "dehumidification rate"],
        patterns=[r"(\d+(?:\.\d+)?\s?L(?:/day)?)"],
    )
    tank_size_text = _extract_spec_field(
        specs=specs_table,
        text=visible_text,
        table_keywords=["tank", "water tank"],
        patterns=[r"tank(?:\s+size)?[:\s]+(\d+(?:\.\d+)?\s?L)", r"(\d+(?:\.\d+)?\s?L)\s+tank"],
    )
    noise_level_text = _extract_spec_field(
        specs=specs_table,
        text=visible_text,
        table_keywords=["noise", "sound"],
        patterns=[r"(\d+(?:\.\d+)?\s?dB)"],
    )
    power_use_text = _extract_spec_field(
        specs=specs_table,
        text=visible_text,
        table_keywords=["power", "input", "watt"],
        patterns=[r"(\d+(?:\.\d+)?\s?W)"],
    )
    warranty_text = _extract_spec_field(
        specs=specs_table,
        text=visible_text,
        table_keywords=["warranty"],
        patterns=[r"(\d+\s*(?:year|years|yr|yrs))\s+warranty", r"warranty[:\s]+(\d+\s*(?:year|years|yr|yrs))"],
    )
    drainage_text = _extract_spec_field(
        specs=specs_table,
        text=visible_text,
        table_keywords=["drain", "drainage", "hose"],
        patterns=[r"(continuous drainage)", r"(drain hose)", r"(built-in pump)", r"(manual tank emptying)"],
    )
    room_size_text = _extract_spec_field(
        specs=specs_table,
        text=visible_text,
        table_keywords=["room size", "coverage", "area"],
        patterns=[r"(\d+\s?(?:m2|sqm|square metres?))"],
    )
    review_rating_text = _extract_spec_field(
        specs=specs_table,
        text=visible_text,
        table_keywords=["rating", "reviews"],
        patterns=[r"(\d(?:\.\d)?\s*(?:/5|stars?))"],
    )
    review_count_text = _extract_spec_field(
        specs=specs_table,
        text=visible_text,
        table_keywords=["review count", "reviews"],
        patterns=[r"(\d[\d,]*)\s+reviews?"],
    )
    spec_fields = [
        capacity_text,
        tank_size_text,
        noise_level_text,
        power_use_text,
        warranty_text,
        drainage_text,
        room_size_text,
    ]
    key_spec_count = sum(1 for value in spec_fields if value != NOT_CONFIRMED)
    confidence_level, confidence_score = calculate_confidence(source_types={source_type}, key_spec_count=key_spec_count)

    return {
        "name": product_name,
        "brand": brand,
        "model_number": model_number,
        "retailer_domain": urlparse(url).netloc,
        "price_text": price_text,
        "capacity_text": capacity_text,
        "tank_size_text": tank_size_text,
        "noise_level_text": noise_level_text,
        "power_use_text": power_use_text,
        "warranty_text": warranty_text,
        "drainage_text": drainage_text,
        "room_size_text": room_size_text,
        "review_rating_text": review_rating_text,
        "review_count_text": review_count_text,
        "description_snippet": _extract_description(soup, visible_text),
        "visible_specs_table": specs_table,
        "confidence_level": confidence_level,
        "confidence_score": confidence_score,
        "common_positives": NOT_CONFIRMED,
        "common_complaints": NOT_CONFIRMED,
        "who_should_buy": NOT_CONFIRMED,
        "who_should_avoid": NOT_CONFIRMED,
        "best_for": NOT_CONFIRMED,
        "bottom_line": NOT_CONFIRMED,
        "extraction_status": "success",
        "extraction_error": None,
        "raw_extracted_json": {
            "source_url": url,
            "source_type": source_type,
            "spec_fields_found": key_spec_count,
            "visible_specs_table": specs_table,
        },
    }


def _collect_source_types(db: Session, product_id: int) -> set[str]:
    rows = db.scalars(select(ArticleJobProduct).where(ArticleJobProduct.product_id == product_id)).all()
    return {row.source_type for row in rows if row.source_type}


def _recalculate_product_confidence(db: Session, product: Product) -> None:
    spec_fields = [
        product.capacity_text,
        product.tank_size_text,
        product.noise_level_text,
        product.power_use_text,
        product.warranty_text,
        product.drainage_text,
        product.room_size_text,
    ]
    key_spec_count = sum(1 for value in spec_fields if value and value != NOT_CONFIRMED)
    source_types = _collect_source_types(db, product.id)
    confidence_level, confidence_score = calculate_confidence(source_types=source_types, key_spec_count=key_spec_count)
    product.confidence_level = confidence_level
    product.confidence_score = confidence_score


def create_article_product_source(db: Session, *, article_job_id: int, source_url: str, source_type: str) -> ArticleJobProduct:
    cleaned_source_url = clean_product_url(source_url)
    link = ArticleJobProduct(
        article_job_id=article_job_id,
        source_url=cleaned_source_url,
        original_source_url=source_url,
        cleaned_source_url=cleaned_source_url,
        source_type=source_type,
        extraction_status="pending",
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def _handle_blocked_extraction(
    db: Session,
    link: ArticleJobProduct,
    *,
    source_url: str,
    method: str,
    reason: str,
    page_title: str | None,
) -> ArticleJobProduct:
    """Record a failed extraction without ever storing blocked-page text as the product name.

    Instead we infer best-effort clues from the URL slug so the user/research step has a
    starting point. All specs stay 'Not confirmed'.
    """
    clues = infer_product_clues_from_url(source_url, page_title)
    safe_name = clues.get("inferred_name") or NOT_CONFIRMED

    product = db.get(Product, link.product_id) if link.product_id else None
    if not product:
        product = Product(
            name=safe_name,
            brand=clues.get("inferred_brand") or NOT_CONFIRMED,
            category=clues.get("category_guess") or "dehumidifier",
            product_url=source_url,
            model_number=clues.get("inferred_model"),
            retailer_domain=clues.get("retailer") or NOT_CONFIRMED,
            extraction_status="extraction_failed",
            extraction_error=reason,
            confidence_level="Low",
            confidence_score=10,
        )
        db.add(product)
        db.commit()
        db.refresh(product)
    else:
        # Never overwrite an existing real name with blocked text; only fill if missing.
        if _is_blank_or_not_confirmed(product.name) and safe_name != NOT_CONFIRMED:
            product.name = safe_name
        product.extraction_status = "extraction_failed"
        product.extraction_error = reason
        db.add(product)
        db.commit()
        db.refresh(product)

    link.product_id = product.id
    link.extraction_status = "extraction_failed"
    link.extraction_error = reason
    link.raw_extracted_json = {
        "method": method,
        "source_type": link.source_type,
        "extraction_failure_reason": reason,
        "inferred_clues": clues,
        "needs_review": True,
        "draft_ready_approved": False,
    }
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def _is_blank_or_not_confirmed(value: str | None) -> bool:
    return value is None or not str(value).strip() or str(value).strip() == NOT_CONFIRMED


def extract_product_for_link(db: Session, link: ArticleJobProduct) -> ArticleJobProduct:
    method = "http"
    source_url = link.cleaned_source_url or link.source_url
    page_title: str | None = None
    try:
        html = _fetch_html_http(source_url)
        if detect_blocked_reason(html=html, visible_text=html, title=None):
            method = "playwright"
            html = _fetch_html_playwright(source_url)

        # Parse once so we can inspect visible text/title for blocked-page detection.
        soup = BeautifulSoup(html or "", "html.parser")
        page_title = _clean_text(soup.title.get_text(" ", strip=True) if soup.title else None)
        visible_text = _clean_text(soup.get_text(" ", strip=True)) if html else None

        blocked_reason = detect_blocked_reason(html=html, visible_text=visible_text, title=page_title)
        if blocked_reason:
            # Do NOT raise/store blocked text. Record a recoverable extraction_failed state.
            return _handle_blocked_extraction(
                db,
                link,
                source_url=source_url,
                method=method,
                reason=blocked_reason,
                page_title=page_title,
            )

        extracted = extract_product_data_from_html(source_url, html, source_type=link.source_type)

        product = db.get(Product, link.product_id) if link.product_id else None
        if not product:
            product = Product(
                name=extracted["name"],
                brand=extracted["brand"],
                category="dehumidifier",
                product_url=source_url,
                notes=None,
            )
        for key, value in extracted.items():
            if hasattr(product, key):
                setattr(product, key, value)
        product.raw_extracted_json = {
            **(product.raw_extracted_json or {}),
            "last_extraction_method": method,
            "last_source_type": link.source_type,
        }
        db.add(product)
        db.commit()
        db.refresh(product)

        link.product_id = product.id
        link.extraction_status = "success"
        link.extraction_error = None
        link.raw_extracted_json = {
            **(link.raw_extracted_json or {}),
            "method": method,
            "source_type": link.source_type,
        }
        _recalculate_product_confidence(db, product)
        db.add(product)
        db.add(link)
        db.commit()
        db.refresh(product)
        db.refresh(link)
        return link
    except Exception as exc:  # noqa: BLE001
        # Network/parse errors are treated as a recoverable extraction failure with clues,
        # not a hard failure that stores junk as the product name.
        reason = str(exc)[:500] or "Product extraction failed."
        return _handle_blocked_extraction(
            db,
            link,
            source_url=source_url,
            method=method,
            reason=reason,
            page_title=page_title,
        )


class ProductResearchError(Exception):
    pass


def approve_product_draft_ready(db: Session, link: ArticleJobProduct) -> ArticleJobProduct:
    """Mark a reviewed card as draft-ready. Requires core fields to be present first."""
    blocking = list(getattr(link, "draft_blocking_missing_fields", []))
    if blocking:
        raise ProductResearchError(
            "Cannot mark draft-ready while core fields are missing: " + ", ".join(blocking)
        )
    link.raw_extracted_json = {
        **(link.raw_extracted_json or {}),
        "draft_ready_approved": True,
        "needs_review": False,
    }
    if link.product is not None and link.product.extraction_status in {
        "extraction_failed",
        "researched_needs_review",
        "research_needed",
    }:
        link.product.extraction_status = "draft_ready"
        db.add(link.product)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


# --- URL verification -------------------------------------------------------
# A realistic browser UA: many AU retailers serve a bot wall to the default UA but
# return the real page to a browser-like request.
_VERIFY_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_VERIFY_TIMEOUT = 20.0
# Status codes that prove a URL is wrong/gone -> reject it.
DEAD_STATUS_CODES = {404, 410}
# Anti-bot / access-control codes: the page very likely exists, we just can't read it.
# Do NOT reject these -> keep but flag as unread (the Big W 403 case).
BLOCKED_STATUS_CODES = {401, 403, 429, 451, 503}

# Verification verdicts.
VERIFY_VERIFIED = "verified"  # live AND mentions the product
VERIFY_UNVERIFIED = "unverified"  # live but product not found in static HTML (e.g. JS-rendered)
VERIFY_BLOCKED = "unverified_blocked"  # anti-bot/JS wall; likely real but unreadable
VERIFY_DEAD = "dead"  # 404/410/4xx -> wrong or gone
VERIFY_ERROR = "error"  # could not connect/timeout -> ambiguous


def _normalise_for_match(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def looks_like_product_match(haystack: str, *, brand: str | None, model: str | None, name: str | None) -> bool:
    """Heuristic: does this page text actually describe the expected product?

    Model number is the strongest signal (matched ignoring spaces/hyphens, so
    'ION632' matches 'ion-632'). Otherwise require brand + a name token, or two
    distinct name tokens.
    """
    norm = _normalise_for_match(haystack)
    if model and model != NOT_CONFIRMED:
        norm_model = _normalise_for_match(model)
        if len(norm_model) >= 3 and norm_model in norm:
            return True
    hay_lower = haystack.lower()
    brand_ok = bool(brand and brand != NOT_CONFIRMED and brand.lower() in hay_lower)
    name_tokens = [
        tok
        for tok in re.split(r"[^a-z0-9]+", (name or "").lower())
        if len(tok) >= 3 and tok not in SLUG_NOISE_TOKENS
    ]
    present = sum(1 for tok in name_tokens if _normalise_for_match(tok) in norm)
    if brand_ok and present >= 1:
        return True
    return present >= 2


def verify_product_url(url: str, *, brand: str | None = None, model: str | None = None, name: str | None = None) -> dict:
    """Fetch a URL and classify it: verified / unverified / unverified_blocked / dead / error.

    Pure (no DB). Returns a JSON-friendly dict suitable for storing in raw_extracted_json.
    """
    result = {"url": url, "status": None, "verification": VERIFY_ERROR, "matched": False, "reason": ""}
    try:
        with httpx.Client(timeout=_VERIFY_TIMEOUT, follow_redirects=True, headers={"User-Agent": _VERIFY_UA}) as client:
            resp = client.get(url)
    except Exception as exc:  # noqa: BLE001 - any network error is just "couldn't verify"
        result["reason"] = f"Could not reach the page: {str(exc)[:120]}"
        return result

    status = resp.status_code
    result["status"] = status
    if status in DEAD_STATUS_CODES:
        result["verification"] = VERIFY_DEAD
        result["reason"] = f"Page not found (HTTP {status})."
        return result
    if status in BLOCKED_STATUS_CODES:
        result["verification"] = VERIFY_BLOCKED
        result["reason"] = f"Page blocked automated access (HTTP {status}); likely real but unread."
        return result
    if status >= 400:
        result["verification"] = VERIFY_DEAD
        result["reason"] = f"Page returned HTTP {status}."
        return result

    html = resp.text or ""
    soup = BeautifulSoup(html, "html.parser")
    title = _clean_text(soup.title.get_text(" ", strip=True) if soup.title else None) or ""
    visible = _clean_text(soup.get_text(" ", strip=True)) or ""
    if detect_blocked_reason(html=html, visible_text=visible, title=title):
        result["verification"] = VERIFY_BLOCKED
        result["reason"] = "Page loaded but served a JS/anti-bot wall; likely real but unread."
        return result

    haystack = f"{title} {visible[:4000]}"
    matched = looks_like_product_match(haystack, brand=brand, model=model, name=name)
    result["matched"] = matched
    if matched:
        result["verification"] = VERIFY_VERIFIED
        result["reason"] = "Page is live and mentions the product."
    else:
        result["verification"] = VERIFY_UNVERIFIED
        result["reason"] = "Page is live but the product name/model was not found in the static HTML."
    return result


def verify_product_urls(
    urls: Iterable[str], *, brand: str | None = None, model: str | None = None, name: str | None = None
) -> list[dict]:
    """Verify a list of URLs, de-duplicating while preserving order."""
    seen: set[str] = set()
    results: list[dict] = []
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        results.append(verify_product_url(url, brand=brand, model=model, name=name))
    return results


def url_is_dead(result: dict) -> bool:
    """A URL we should drop (wrong/gone). Blocked/unverified are kept."""
    return result.get("verification") == VERIFY_DEAD


def has_publishable_url(results: Iterable[dict]) -> bool:
    """True if at least one URL is confirmed live (verified). Used by auto-approve gating."""
    return any(r.get("verification") == VERIFY_VERIFIED for r in results)


MAX_RESEARCH_SOURCES = 5
RESEARCH_SNIPPET_LIMIT = 1500


def _gather_accessible_sources(query: str, *, exclude_url: str | None = None) -> tuple[list[dict], float | None]:
    """Search for the inferred product and fetch a few accessible pages.

    Returns (sources, cost). Blocked/anti-bot pages are skipped, never stored.
    Only sources we could actually read are returned.
    """
    from app.services.dataforseo import DataForSEOClient, parse_serp_items

    client = DataForSEOClient()
    serp = client.fetch_google_serp(query)
    rows, _extras = parse_serp_items(serp.result)
    organic = [row for row in rows if row.get("result_type") == "organic" and row.get("url")]

    sources: list[dict] = []
    for row in organic:
        if len(sources) >= MAX_RESEARCH_SOURCES:
            break
        url = row["url"]
        # Always keep the search snippet (accessible by definition) even if the page itself blocks us.
        snippet = _clean_text(row.get("snippet")) or ""
        page_text = ""
        try:
            html = _fetch_html_http(url)
            soup = BeautifulSoup(html or "", "html.parser")
            title = _clean_text(soup.title.get_text(" ", strip=True) if soup.title else None)
            visible = _clean_text(soup.get_text(" ", strip=True)) if html else None
            if not detect_blocked_reason(html=html, visible_text=visible, title=title):
                page_text = (visible or "")[:RESEARCH_SNIPPET_LIMIT]
        except Exception:  # noqa: BLE001 - a single unreachable source is not fatal
            page_text = ""
        combined = _clean_text(f"{snippet} {page_text}") or ""
        if not combined:
            continue
        sources.append(
            {
                "url": url,
                "domain": row.get("domain"),
                "title": _clean_text(row.get("title")),
                "text": combined[:RESEARCH_SNIPPET_LIMIT],
            }
        )
    return sources, serp.cost


def _apply_research_to_product(product: Product, consolidated: dict) -> None:
    """Map consolidated research fields onto the Product, keeping unknowns as Not confirmed."""

    def value_or_keep(new_value, current) -> str | None:
        cleaned = _clean_text(str(new_value)) if new_value is not None else None
        if not cleaned or cleaned == NOT_CONFIRMED:
            return current
        return cleaned

    if not _is_blank_or_not_confirmed(consolidated.get("product_name")):
        if _is_blank_or_not_confirmed(product.name):
            product.name = _clean_text(str(consolidated["product_name"])) or product.name
    product.brand = value_or_keep(consolidated.get("brand"), product.brand)
    product.model_number = value_or_keep(consolidated.get("model"), product.model_number)
    if not _is_blank_or_not_confirmed(consolidated.get("category")):
        product.category = _clean_text(str(consolidated["category"])) or product.category
    product.price_text = value_or_keep(consolidated.get("price_or_price_range"), product.price_text)
    product.capacity_text = value_or_keep(consolidated.get("capacity_or_key_size"), product.capacity_text)
    product.best_for = value_or_keep(consolidated.get("best_for"), product.best_for)

    pros = consolidated.get("pros")
    if isinstance(pros, list) and pros:
        product.common_positives = "; ".join(str(item) for item in pros if str(item).strip())
    cons = consolidated.get("cons")
    if isinstance(cons, list) and cons:
        product.common_complaints = "; ".join(str(item) for item in cons if str(item).strip())

    key_specs = consolidated.get("key_specs")
    if isinstance(key_specs, list) and key_specs:
        existing = product.visible_specs_table if isinstance(product.visible_specs_table, dict) else {}
        product.visible_specs_table = {**existing, "researched_key_specs": [str(s) for s in key_specs]}


def research_product_for_link(db: Session, link: ArticleJobProduct) -> ArticleJobProduct:
    """Build a draft product card from accessible sources when direct extraction failed.

    Never invents specs/prices. Result is always needs_review until a human approves.
    """
    from app.services.anthropic_client import AnthropicClient

    source_url = link.cleaned_source_url or link.source_url
    raw = link.raw_extracted_json or {}
    clues = raw.get("inferred_clues") or infer_product_clues_from_url(source_url, None)

    query_parts = [clues.get("inferred_brand"), clues.get("inferred_name"), clues.get("inferred_model")]
    query = _clean_text(" ".join(part for part in query_parts if part)) or clues.get("inferred_name") or ""
    if not query:
        raise ProductResearchError("No product clues available to research. Edit the card manually.")
    if clues.get("category_guess") and clues["category_guess"] not in query.lower():
        query = f"{query} {clues['category_guess']}"

    try:
        sources, _cost = _gather_accessible_sources(query, exclude_url=source_url)
    except Exception as exc:  # noqa: BLE001
        raise ProductResearchError(f"Product research search failed: {exc}") from exc

    consolidated: dict = {}
    if sources:
        user_prompt = (
            "INFERRED_CLUES:\n"
            + "\n".join(f"- {key}: {value}" for key, value in clues.items())
            + "\n\nACCESSIBLE_SOURCES:\n"
            + "\n\n".join(
                f"[{idx + 1}] {src.get('title') or src.get('domain')} ({src['url']})\n{src['text']}"
                for idx, src in enumerate(sources)
            )
        )
        try:
            client = AnthropicClient()
            consolidated = client.generate_json(
                system_prompt=_read_prompt("product_research_prompt.md"),
                user_prompt=user_prompt,
                max_tokens=2000,
            )
        except Exception as exc:  # noqa: BLE001
            raise ProductResearchError(f"Product research consolidation failed: {exc}") from exc

    product = db.get(Product, link.product_id) if link.product_id else None
    if not product:
        product = Product(
            name=clues.get("inferred_name") or NOT_CONFIRMED,
            brand=clues.get("inferred_brand") or NOT_CONFIRMED,
            category=clues.get("category_guess") or "dehumidifier",
            product_url=source_url,
            model_number=clues.get("inferred_model"),
            retailer_domain=clues.get("retailer") or NOT_CONFIRMED,
        )
        db.add(product)
        db.commit()
        db.refresh(product)

    if consolidated:
        _apply_research_to_product(product, consolidated)
    product.extraction_status = "researched_needs_review"
    product.extraction_error = None
    _recalculate_product_confidence(db, product)
    db.add(product)
    db.commit()
    db.refresh(product)

    link.product_id = product.id
    link.extraction_status = "researched_needs_review"
    link.extraction_error = None
    link.raw_extracted_json = {
        **(link.raw_extracted_json or {}),
        "inferred_clues": clues,
        "needs_review": True,
        "draft_ready_approved": False,
        "research_query": query,
        "research_sources": consolidated.get("research_sources")
        if isinstance(consolidated.get("research_sources"), list)
        else [{"url": s["url"], "domain": s.get("domain"), "used_for": "research"} for s in sources],
        "uncertain_fields": consolidated.get("uncertain_fields") if isinstance(consolidated.get("uncertain_fields"), list) else [],
        "research_notes": consolidated.get("notes") if isinstance(consolidated.get("notes"), str) else None,
        "researched": True,
    }
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


# --- Web-search research (Phase 4) -----------------------------------------

WEBSEARCH_RESEARCH_PROMPT = "product_research_websearch_prompt.md"


def _ws_value(new_value, current, *, limit: int | None = None) -> str | None:
    """Non-destructive map: keep current if the new value is blank/Not confirmed."""
    cleaned = _clean_text(str(new_value)) if new_value is not None else None
    if not cleaned or cleaned == NOT_CONFIRMED:
        return current
    return cleaned[:limit] if limit else cleaned


def _ws_join(items) -> str | None:
    if not isinstance(items, list):
        return None
    parts = [
        cleaned
        for cleaned in (_clean_text(str(item)) for item in items)
        if cleaned and cleaned != NOT_CONFIRMED
    ]
    return "; ".join(parts) if parts else None


def _apply_websearch_research_to_product(product: Product, data: dict) -> None:
    """Map the rich web-search research JSON onto the Product. Never overwrites a
    confirmed value with a blank/Not confirmed one. Truncates String(255) columns."""
    if not _is_blank_or_not_confirmed(data.get("product_name")) and _is_blank_or_not_confirmed(product.name):
        product.name = (_clean_text(str(data["product_name"])) or product.name)[:255]
    product.brand = _ws_value(data.get("brand"), product.brand, limit=255)
    product.model_number = _ws_value(data.get("model"), product.model_number, limit=255)
    if not _is_blank_or_not_confirmed(data.get("category")):
        product.category = (_clean_text(str(data["category"])) or product.category)[:255]

    # Spec fields are String(255).
    product.price_range_text = _ws_value(data.get("price_range_text"), product.price_range_text, limit=255)
    if product.price_range_text and _is_blank_or_not_confirmed(product.price_text):
        product.price_text = product.price_range_text[:255]
    product.capacity_text = _ws_value(data.get("capacity_text"), product.capacity_text, limit=255)
    product.tank_size_text = _ws_value(data.get("tank_size_text"), product.tank_size_text, limit=255)
    product.noise_level_text = _ws_value(data.get("noise_level_text"), product.noise_level_text, limit=255)
    product.power_use_text = _ws_value(data.get("power_use_text"), product.power_use_text, limit=255)
    product.warranty_text = _ws_value(data.get("warranty_text"), product.warranty_text, limit=255)
    product.drainage_text = _ws_value(data.get("drainage_text"), product.drainage_text, limit=255)
    product.room_size_text = _ws_value(data.get("room_size_text"), product.room_size_text, limit=255)
    product.review_rating_text = _ws_value(data.get("review_rating_text"), product.review_rating_text, limit=255)
    product.review_count_text = _ws_value(data.get("review_count_text"), product.review_count_text, limit=255)
    product.australian_availability = _ws_value(
        data.get("australian_availability"), product.australian_availability, limit=255
    )

    # Text fields (unbounded).
    product.description_snippet = _ws_value(data.get("description_snippet"), product.description_snippet)
    product.best_for = _ws_value(data.get("best_for"), product.best_for)
    product.who_should_buy = _ws_value(data.get("who_should_buy"), product.who_should_buy)
    product.who_should_avoid = _ws_value(data.get("who_should_avoid"), product.who_should_avoid)
    product.bottom_line = _ws_value(data.get("bottom_line"), product.bottom_line)
    product.reliability_concerns = _ws_value(data.get("reliability_concerns"), product.reliability_concerns)
    product.review_methodology_notes = _ws_value(
        data.get("review_methodology_notes"), product.review_methodology_notes
    )

    # List -> "; "-joined text fields.
    for field, key in (
        ("common_positives", "common_positives"),
        ("common_complaints", "common_complaints"),
        ("positive_review_patterns", "positive_review_patterns"),
        ("negative_review_patterns", "negative_review_patterns"),
    ):
        joined = _ws_join(data.get(key))
        if joined:
            setattr(product, field, joined)

    key_specs = data.get("key_specs")
    if isinstance(key_specs, list) and key_specs:
        product.key_specs = [str(spec) for spec in key_specs if str(spec).strip()]


def _verify_and_collect_retailer_urls(
    consolidated: dict, *, brand: str | None, model: str | None, name: str | None, current_date: str
) -> tuple[list[dict], list[dict]]:
    """Verify each retailer URL the model returned. Drop dead links; keep the rest
    with their verdict attached. Returns (kept_retailers, all_verification_results)."""
    entries = consolidated.get("retailer_urls") if isinstance(consolidated.get("retailer_urls"), list) else []
    kept: list[dict] = []
    verifications: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = _clean_text(str(entry.get("url") or ""))
        if not url:
            continue
        verdict = verify_product_url(url, brand=brand, model=model, name=name)
        verifications.append(verdict)
        if url_is_dead(verdict):
            continue  # wrong/gone -> never store it
        kept.append(
            {
                "retailer": _clean_text(str(entry.get("retailer") or "")) or None,
                "url": url,
                "price_aud": _clean_text(str(entry.get("price_aud") or "")) or NOT_CONFIRMED,
                "as_of": _clean_text(str(entry.get("as_of") or "")) or current_date,
                "verification": verdict["verification"],
                "status": verdict["status"],
            }
        )
    return kept, verifications


def research_product_via_websearch(
    db: Session, link: ArticleJobProduct, *, current_date: str | None = None, auto_approve: bool = True
) -> ArticleJobProduct:
    """Build a product card using OpenAI web search, verify its URLs, and (optionally)
    auto-approve the card as draft-ready when core fields are present and at least one
    URL verifies live. Never invents data; unconfirmed facts stay 'Not confirmed'."""
    from app.services.openai_client import OpenAIClient, OpenAIError, web_search_fired

    source_url = link.cleaned_source_url or link.source_url
    raw = link.raw_extracted_json or {}
    product = db.get(Product, link.product_id) if link.product_id else None
    clues = raw.get("inferred_clues") or infer_product_clues_from_url(source_url, None)

    def _identity(attr: str | None, clue: str | None, default: str = NOT_CONFIRMED) -> str:
        if attr and not _is_blank_or_not_confirmed(attr):
            return attr
        return clue or default

    name = _identity(getattr(product, "name", None), clues.get("inferred_name"))
    brand = _identity(getattr(product, "brand", None), clues.get("inferred_brand"))
    model = _identity(getattr(product, "model_number", None), clues.get("inferred_model"))
    category = _identity(getattr(product, "category", None), clues.get("category_guess"), default="dehumidifier")

    candidate_urls: list[str] = []
    for url in (source_url, getattr(product, "product_url", None), getattr(product, "manufacturer_url", None)):
        if url and url not in candidate_urls:
            candidate_urls.append(url)
    if product and isinstance(product.retailer_urls, list):
        for entry in product.retailer_urls:
            url = entry.get("url") if isinstance(entry, dict) else None
            if url and url not in candidate_urls:
                candidate_urls.append(url)

    cur = current_date or date.today().isoformat()
    identity = f"name={name}; brand={brand}; model={model}; category={category}"
    candidate_block = "\n".join(f"- {url}" for url in candidate_urls) or "(none)"
    input_text = f"PRODUCT_IDENTITY: {identity}\nCANDIDATE_URLS:\n{candidate_block}\nCURRENT_DATE: {cur}"

    try:
        client = OpenAIClient()
        response = client.generate_json_with_web_search(
            instructions=_read_prompt(WEBSEARCH_RESEARCH_PROMPT),
            input_text=input_text,
        )
    except OpenAIError as exc:
        raise ProductResearchError(f"Web-search product research failed: {exc}") from exc

    consolidated = response.parsed_json if isinstance(response.parsed_json, dict) else {}
    if not consolidated:
        raise ProductResearchError("Web-search research returned no usable JSON.")

    if not product:
        product = Product(
            name=clues.get("inferred_name") or NOT_CONFIRMED,
            brand=clues.get("inferred_brand") or NOT_CONFIRMED,
            category=category,
            product_url=source_url,
            model_number=clues.get("inferred_model"),
            retailer_domain=clues.get("retailer") or NOT_CONFIRMED,
        )
        db.add(product)
        db.commit()
        db.refresh(product)

    _apply_websearch_research_to_product(product, consolidated)

    match_name = product.name if not _is_blank_or_not_confirmed(product.name) else (None if name == NOT_CONFIRMED else name)
    match_brand = product.brand if not _is_blank_or_not_confirmed(product.brand) else (None if brand == NOT_CONFIRMED else brand)
    match_model = product.model_number or (None if model == NOT_CONFIRMED else model)

    kept_retailers, url_verifications = _verify_and_collect_retailer_urls(
        consolidated, brand=match_brand, model=match_model, name=match_name, current_date=cur
    )
    if kept_retailers:
        product.retailer_urls = kept_retailers

    manufacturer_url = _clean_text(str(consolidated.get("manufacturer_url") or ""))
    if manufacturer_url and manufacturer_url != NOT_CONFIRMED:
        man_verdict = verify_product_url(manufacturer_url, brand=match_brand, model=match_model, name=match_name)
        url_verifications.append(man_verdict)
        if not url_is_dead(man_verdict):
            product.manufacturer_url = manufacturer_url[:1000]

    if _is_blank_or_not_confirmed(product.price_text):
        priced = next((r for r in kept_retailers if r["price_aud"] != NOT_CONFIRMED), None)
        if priced:
            product.price_text = priced["price_aud"][:255]

    product.extraction_status = "researched_needs_review"
    product.extraction_error = None
    _recalculate_product_confidence(db, product)
    db.add(product)
    db.commit()
    db.refresh(product)

    link.product_id = product.id
    link.extraction_status = "researched_needs_review"
    link.extraction_error = None
    link.raw_extracted_json = {
        **(link.raw_extracted_json or {}),
        "inferred_clues": clues,
        "needs_review": True,
        "draft_ready_approved": False,
        "research_provider": "openai_web_search",
        "research_query": identity,
        "research_searched": web_search_fired(response.response_json),
        "research_sources": consolidated.get("research_sources")
        if isinstance(consolidated.get("research_sources"), list)
        else [],
        "uncertain_fields": consolidated.get("uncertain_fields")
        if isinstance(consolidated.get("uncertain_fields"), list)
        else [],
        "research_notes": consolidated.get("review_methodology_notes")
        if isinstance(consolidated.get("review_methodology_notes"), str)
        else None,
        "url_verifications": url_verifications,
        "researched": True,
    }
    db.add(link)
    db.commit()
    db.refresh(link)

    # Auto-approve only when core fields are present AND at least one URL verified live.
    if auto_approve:
        blocking = list(getattr(link, "draft_blocking_missing_fields", []))
        if not blocking and has_publishable_url(url_verifications):
            try:
                approve_product_draft_ready(db, link)
            except ProductResearchError:
                pass  # leave as researched_needs_review for manual review
        db.refresh(link)
    return link


# --- Web-search product discovery (Phase 5) --------------------------------

DISCOVERY_PROMPT = "product_discovery_prompt.md"
MAX_DISCOVERED_PRODUCTS = 5


def _product_identity_key(name: str | None, brand: str | None) -> str:
    return _normalise_for_match(f"{name or ''}{brand or ''}")


def _existing_product_keys(db: Session, article_job_id: int) -> set[str]:
    links = db.scalars(
        select(ArticleJobProduct)
        .where(ArticleJobProduct.article_job_id == article_job_id)
        .options(selectinload(ArticleJobProduct.product))
    ).all()
    keys: set[str] = set()
    for existing in links:
        product = existing.product
        if product:
            keys.add(_product_identity_key(product.name, product.brand))
    return keys


def discover_products_via_websearch(
    db: Session, job, *, max_products: int = MAX_DISCOVERED_PRODUCTS
) -> list[ArticleJobProduct]:
    """Find 3-5 Australian products for a money page via OpenAI web search and create a
    product link (with a topic-chosen role) for each new one. Does NOT research the cards —
    the caller runs research_product_via_websearch on the returned links. Skips products
    already linked to the job."""
    from app.services.openai_client import OpenAIClient, OpenAIError

    existing_keys = _existing_product_keys(db, job.id)
    existing_names = sorted({key for key in existing_keys})

    input_text = (
        f"ARTICLE_TOPIC: {job.title}\n"
        f"PRIMARY_KEYWORD: {job.primary_keyword}\n"
        "TARGET_COUNTRY: Australia\n"
        f"OPTIONAL_CONTEXT: already linked (avoid duplicates): {', '.join(existing_names) if existing_names else '(none)'}"
    )

    try:
        client = OpenAIClient()
        response = client.generate_json_with_web_search(
            instructions=_read_prompt(DISCOVERY_PROMPT),
            input_text=input_text,
        )
    except OpenAIError as exc:
        raise ProductResearchError(f"Product discovery search failed: {exc}") from exc

    payload = response.parsed_json if isinstance(response.parsed_json, dict) else {}
    products = payload.get("products") if isinstance(payload.get("products"), list) else []
    if not products:
        raise ProductResearchError("Product discovery returned no products.")

    created: list[ArticleJobProduct] = []
    seen_keys = set(existing_keys)
    for entry in products:
        if len(created) >= max_products:
            break
        if not isinstance(entry, dict):
            continue
        name = _clean_text(str(entry.get("name") or ""))
        if not name or name == NOT_CONFIRMED:
            continue
        brand = _clean_text(str(entry.get("brand") or "")) or NOT_CONFIRMED
        key = _product_identity_key(name, brand if brand != NOT_CONFIRMED else None)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        candidate_urls = entry.get("candidate_urls") if isinstance(entry.get("candidate_urls"), list) else []
        first_url = ""
        for url_entry in candidate_urls:
            if isinstance(url_entry, dict) and url_entry.get("url"):
                first_url = _clean_text(str(url_entry["url"])) or ""
                if first_url:
                    break
        cleaned_url = clean_product_url(first_url) if first_url else None

        product = Product(
            name=name[:255],
            brand=brand[:255],
            category=(_clean_text(str(entry.get("category") or "")) or "dehumidifier")[:255],
            role=(_clean_text(str(entry.get("role") or "")) or None),
            product_url=cleaned_url or first_url or None,
            model_number=_clean_text(str(entry.get("model") or "")) if entry.get("model") not in (None, NOT_CONFIRMED) else None,
            retailer_domain=(urlparse(first_url).netloc or NOT_CONFIRMED) if first_url else NOT_CONFIRMED,
            extraction_status="research_needed",
            confidence_level="Low",
            confidence_score=20,
        )
        db.add(product)
        db.commit()
        db.refresh(product)

        link = ArticleJobProduct(
            article_job_id=job.id,
            product_id=product.id,
            source_url=cleaned_url or first_url or "",
            original_source_url=first_url or None,
            cleaned_source_url=cleaned_url,
            source_type="discovered",
            extraction_status="research_needed",
            raw_extracted_json={
                "needs_review": True,
                "draft_ready_approved": False,
                "discovered": True,
                "discovery_provider": "openai_web_search",
                "role": product.role,
                "role_rationale": _clean_text(str(entry.get("role_rationale") or "")) or None,
                "why_recommended": _clean_text(str(entry.get("why_recommended") or "")) or None,
                "candidate_urls": [
                    {"retailer": _clean_text(str(u.get("retailer") or "")) or None, "url": _clean_text(str(u.get("url") or ""))}
                    for u in candidate_urls
                    if isinstance(u, dict) and u.get("url")
                ],
            },
        )
        db.add(link)
        db.commit()
        db.refresh(link)
        created.append(link)

    return created
