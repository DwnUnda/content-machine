from __future__ import annotations

import re
from collections import Counter

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import CompetitorPage, SerpResult


TIMEOUT_SECONDS = 15.0
MAX_VISIBLE_TEXT_CHARS = 4000
TOP_ORGANIC_LIMIT = 5

AUSTRALIAN_SIGNALS = [
    ".com.au",
    "australia",
    "australian",
    "aud",
    "mould",
    "brisbane",
    "queensland",
    "sydney",
    "melbourne",
    "coastal",
    "rental",
    "laundry",
]

AUSTRALIAN_RETAILERS = [
    "harvey norman",
    "the good guys",
    "bing lee",
    "jb hi-fi",
    "appliances online",
    "big w",
    "kogan",
]

QUESTION_PREFIXES = ("what", "why", "how", "when", "can", "does", "is", "are", "which", "who")


def classify_page_type(url: str, title: str | None, text: str) -> str:
    lower_url = url.lower()
    lower_title = (title or "").lower()
    lower_text = text.lower()
    if any(token in lower_url for token in [".gov.au", "health.gov", "nhs", "department-of-health"]):
        return "government/health source"
    if any(token in lower_url for token in ["forum", "reddit.com", "community", "whirlpool.net.au"]):
        return "forum/community"
    if any(token in lower_url for token in ["news", "abc.net.au/news", "theguardian", "smh.com.au"]):
        return "news/media"
    if any(token in lower_text for token in ["add to cart", "buy now", "in stock", "shop now", "$", "aud"]) or any(
        token in lower_url for token in ["product", "category", "shop", "store"]
    ):
        return "retailer"
    if any(token in lower_text for token in ["official site", "manufacturer", "our product", "warranty"]) or any(
        token in lower_url for token in ["support", "official", "brand"]
    ):
        return "manufacturer"
    if any(token in lower_title for token in ["best", "review", "reviews", "comparison", "vs"]) or any(
        token in lower_text for token in ["affiliate", "commission", "we may earn", "best for", "who should buy"]
    ):
        return "affiliate/review site"
    if any(token in lower_text for token in ["blog", "guide", "explained", "tips", "how to"]):
        return "informational blog"
    return "unknown"


def score_australian_relevance(url: str, text: str) -> tuple[int, list[str]]:
    lower_url = url.lower()
    lower_text = text.lower()
    score = 0
    signals: list[str] = []
    if ".com.au" in lower_url:
        score += 25
        signals.append(".com.au domain")
    if "australia" in lower_text or "australian" in lower_text:
        score += 20
        signals.append("Australia/Australian mention")
    if "aud" in lower_text or "$" in text:
        score += 10
        signals.append("AUD/$ pricing")
    for retailer in AUSTRALIAN_RETAILERS:
        if retailer in lower_text:
            score += 10
            signals.append(f"mentions {retailer}")
            break
    if "mould" in lower_text:
        score += 10
        signals.append("uses mould spelling")
    for token in ["brisbane", "queensland", "sydney", "melbourne", "coastal", "rental", "laundry"]:
        if token in lower_text:
            score += 5
            signals.append(f"mentions {token}")
    return min(score, 100), signals


def detect_product_names(headings: list[str], visible_text: str) -> list[str]:
    candidates = set()
    pattern = re.compile(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z0-9][a-zA-Z0-9\-]+){1,4})\b")
    for text in headings + re.findall(r".{0,80}", visible_text[:1200]):
        for match in pattern.findall(text):
            if any(token in match.lower() for token in ["australia", "humid", "mould", "review", "guide", "brisbane"]):
                continue
            if len(match.split()) >= 2:
                candidates.add(match.strip())
    return sorted(candidates)[:15]


def extract_page_data_from_html(url: str, html: str, *, extraction_method: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    meta_description_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = meta_description_tag.get("content", "").strip() if meta_description_tag else None
    h1 = soup.find("h1")
    h1_text = h1.get_text(" ", strip=True) if h1 else None
    h2_list = [node.get_text(" ", strip=True) for node in soup.find_all("h2") if node.get_text(" ", strip=True)]
    h3_list = [node.get_text(" ", strip=True) for node in soup.find_all("h3") if node.get_text(" ", strip=True)]
    visible_text = soup.get_text(" ", strip=True)
    visible_text = re.sub(r"\s+", " ", visible_text).strip()
    visible_text_extract = visible_text[:MAX_VISIBLE_TEXT_CHARS]
    word_count = len(visible_text.split()) if visible_text else 0
    faq_headings = [
        heading
        for heading in [h1_text, *h2_list, *h3_list]
        if heading and ("faq" in heading.lower() or heading.strip().endswith("?") or heading.lower().startswith(QUESTION_PREFIXES))
    ]
    headings = [text for text in [h1_text, *h2_list, *h3_list] if text]
    products = detect_product_names(headings, visible_text_extract)
    tables_count = len(soup.find_all("table"))
    affiliate_indicators = [
        phrase
        for phrase in ["affiliate", "commission", "best for", "buy now", "shop now"]
        if phrase in visible_text.lower()
    ]
    page_type = classify_page_type(url, title, visible_text)
    au_score, au_signals = score_australian_relevance(url, visible_text)
    return {
        "title": title,
        "meta_description": meta_description,
        "h1": h1_text,
        "h2_list": h2_list,
        "h3_list": h3_list,
        "word_count_estimate": word_count,
        "visible_text_extract": visible_text_extract,
        "detected_product_names": products,
        "tables_count": tables_count,
        "faq_headings": faq_headings,
        "affiliate_indicators": affiliate_indicators,
        "australian_relevance_signals": au_signals,
        "australian_relevance_score": au_score,
        "page_type": page_type,
        "extraction_method": extraction_method,
        "extraction_status": "success",
        "error_message": None,
        "raw_extracted_data_json": {
            "headings": headings,
            "product_names": products,
            "faq_headings": faq_headings,
        },
    }


def _fetch_html_http(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 HomeDryLabContentMachine/1.0"}
    with httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def _fetch_html_playwright(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Playwright fallback unavailable.") from exc
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        timeout_ms = int(TIMEOUT_SECONDS * 1000)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception as exc:  # noqa: BLE001
            if "Timeout" not in str(exc):
                browser.close()
                raise
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        try:
            page.wait_for_timeout(1500)
        except Exception:
            pass
        html = page.content()
        browser.close()
    return html


def extract_competitors_for_job(db: Session, article_job_id: int) -> list[CompetitorPage]:
    serp_rows = list(
        db.scalars(
            select(SerpResult)
            .where(SerpResult.article_job_id == article_job_id, SerpResult.result_type == "organic")
            .order_by(SerpResult.position.asc(), SerpResult.created_at.desc())
        ).all()
    )
    selected: list[SerpResult] = []
    seen_urls = set()
    for row in serp_rows:
        if row.url and row.url not in seen_urls:
            selected.append(row)
            seen_urls.add(row.url)
        if len(selected) >= TOP_ORGANIC_LIMIT:
            break

    created: list[CompetitorPage] = []
    for row in selected:
        method = "http"
        try:
            html = _fetch_html_http(row.url)
            if not html or len(html.strip()) < 300:
                method = "playwright"
                html = _fetch_html_playwright(row.url)
            data = extract_page_data_from_html(row.url, html, extraction_method=method)
            competitor = CompetitorPage(
                article_job_id=article_job_id,
                serp_result_id=row.id,
                url=row.url,
                domain=row.domain,
                **data,
            )
        except Exception as exc:  # noqa: BLE001
            competitor = CompetitorPage(
                article_job_id=article_job_id,
                serp_result_id=row.id,
                title=row.title,
                url=row.url,
                domain=row.domain,
                page_type="unknown",
                extraction_method=method if method else "failed",
                extraction_status="failed",
                error_message=str(exc)[:500],
                raw_extracted_data_json={"serp_title": row.title, "serp_snippet": row.snippet},
            )
        db.add(competitor)
        created.append(competitor)
    db.commit()
    for competitor in created:
        db.refresh(competitor)
    return created


def summarize_page_types(rows: list[CompetitorPage]) -> dict[str, int]:
    counter = Counter(row.page_type or "unknown" for row in rows)
    return dict(counter)
