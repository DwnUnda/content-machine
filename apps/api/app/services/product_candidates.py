from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlparse

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    ArticleJob,
    ArticleJobProduct,
    CompetitorAnalysisReport,
    CompetitorPage,
    KeywordResearch,
    Product,
    ProductCandidate,
    SerpResult,
)
from app.services.dataforseo import DataForSEOClient, DataForSEOError
from app.services.product_research import NOT_CONFIRMED, clean_product_url, extract_product_for_link


MAX_PAID_DISCOVERY_SEARCHES = 3
TARGET_CANDIDATE_COUNT = 8
KNOWN_RETAILERS = {
    "appliancesonline.com.au": "Appliances Online",
    "thegoodguys.com.au": "The Good Guys",
    "bunnings.com.au": "Bunnings",
    "harveynorman.com.au": "Harvey Norman",
    "binglee.com.au": "Bing Lee",
    "kogan.com": "Kogan",
}


class ProductCandidateError(Exception):
    pass


@dataclass(slots=True)
class CandidateSeed:
    product_name: str
    brand: str | None = None
    model_number: str | None = None
    source_url: str | None = None
    source_domain: str | None = None
    source_type: str = "existing_data"
    reasons: list[str] = field(default_factory=list)
    found_count: int = 1
    confidence_score: int = 50
    suggested_best_for: str | None = None
    raw_items: list[dict] = field(default_factory=list)


def _normalise_key(name: str, brand: str | None, model_number: str | None) -> str:
    value = " ".join(part for part in [brand or "", name or "", model_number or ""] if part)
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", value).strip() or None


def _parse_brand_and_model(product_name: str) -> tuple[str | None, str | None]:
    parts = product_name.split()
    brand = parts[0] if parts else None
    model_match = re.search(r"\b([A-Z0-9]{2,}(?:[- ][A-Z0-9]{2,})+)\b", product_name)
    model_number = model_match.group(1) if model_match else None
    return brand, model_number


def _extract_candidate_names(text: str) -> list[str]:
    pattern = re.compile(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z0-9][a-zA-Z0-9\-]+){1,4})\b")
    banned = {"Australia", "Australian", "Queensland", "Sydney", "Melbourne", "Brisbane"}
    names: list[str] = []
    for match in pattern.findall(text):
        cleaned = _clean_text(match)
        if not cleaned or cleaned in banned:
            continue
        lower = cleaned.lower()
        if any(token in lower for token in ["mould", "dehumidifier", "humidifier", "review", "guide", "best for"]):
            continue
        if len(cleaned.split()) < 2:
            continue
        names.append(cleaned)
    return names


def _suggested_best_for(job: ArticleJob) -> str:
    keyword = job.primary_keyword.lower()
    if "mould" in keyword:
        return "Australian homes dealing with mould-prone rooms and damp air"
    if "laundry" in keyword:
        return "Laundry drying and damp-prone utility spaces"
    return "Australian households comparing dehumidifier options"


def _merge_seed(target: CandidateSeed, seed: CandidateSeed) -> None:
    target.found_count += seed.found_count
    target.confidence_score = min(100, max(target.confidence_score, seed.confidence_score) + 5)
    for reason in seed.reasons:
        if reason not in target.reasons:
            target.reasons.append(reason)
    for raw in seed.raw_items:
        target.raw_items.append(raw)
    if not target.source_url and seed.source_url:
        target.source_url = seed.source_url
    if not target.source_domain and seed.source_domain:
        target.source_domain = seed.source_domain
    if target.source_type == "existing_data" and seed.source_type != "existing_data":
        target.source_type = seed.source_type
    if not target.brand and seed.brand:
        target.brand = seed.brand
    if not target.model_number and seed.model_number:
        target.model_number = seed.model_number


def _seed_from_competitors(job: ArticleJob, competitors: list[CompetitorPage]) -> dict[str, CandidateSeed]:
    seeds: dict[str, CandidateSeed] = {}
    suggested_best_for = _suggested_best_for(job)
    for competitor in competitors:
        names = list(competitor.detected_product_names or [])
        text_sources = [competitor.title or "", competitor.h1 or "", " ".join(competitor.h2_list or [])]
        for text in text_sources:
            names.extend(_extract_candidate_names(text))
        for name in names:
            brand, model_number = _parse_brand_and_model(name)
            key = _normalise_key(name, brand, model_number)
            seed = CandidateSeed(
                product_name=name,
                brand=brand,
                model_number=model_number,
                source_url=competitor.url,
                source_domain=competitor.domain,
                source_type="competitor",
                reasons=[f"Found on competitor page: {competitor.domain or 'unknown source'}"],
                found_count=1,
                confidence_score=60,
                suggested_best_for=suggested_best_for,
                raw_items=[{"competitor_page_id": competitor.id, "page_type": competitor.page_type}],
            )
            if key in seeds:
                _merge_seed(seeds[key], seed)
            else:
                seeds[key] = seed
    return seeds


def _seed_from_analysis(job: ArticleJob, analysis: CompetitorAnalysisReport | None) -> dict[str, CandidateSeed]:
    seeds: dict[str, CandidateSeed] = {}
    if not analysis:
        return seeds
    suggested_best_for = _suggested_best_for(job)
    for name in analysis.repeated_products_json or []:
        brand, model_number = _parse_brand_and_model(name)
        key = _normalise_key(name, brand, model_number)
        seeds[key] = CandidateSeed(
            product_name=name,
            brand=brand,
            model_number=model_number,
            source_type="existing_data",
            reasons=["Repeated product mention across analysed competitors"],
            found_count=2,
            confidence_score=70,
            suggested_best_for=suggested_best_for,
            raw_items=[{"analysis_report_id": analysis.id}],
        )
    return seeds


def _seed_from_serp(job: ArticleJob, serp_results: list[SerpResult]) -> dict[str, CandidateSeed]:
    seeds: dict[str, CandidateSeed] = {}
    suggested_best_for = _suggested_best_for(job)
    for row in serp_results:
        if row.result_type != "organic":
            continue
        names: list[str] = []
        for text in [row.title or "", row.snippet or ""]:
            names.extend(_extract_candidate_names(text))
        for name in names:
            brand, model_number = _parse_brand_and_model(name)
            key = _normalise_key(name, brand, model_number)
            seed = CandidateSeed(
                product_name=name,
                brand=brand,
                model_number=model_number,
                source_url=row.url,
                source_domain=row.domain,
                source_type="existing_data",
                reasons=[f"Found in SERP title/snippet: {row.domain or 'unknown domain'}"],
                found_count=1,
                confidence_score=45,
                suggested_best_for=suggested_best_for,
                raw_items=[{"serp_result_id": row.id}],
            )
            if key in seeds:
                _merge_seed(seeds[key], seed)
            else:
                seeds[key] = seed
    return seeds


def _candidate_search_queries(job: ArticleJob) -> list[str]:
    keyword = job.primary_keyword.strip()
    return [
        f"{keyword} product Australia",
        f"{keyword} appliances online",
        f"{keyword} the good guys",
    ][:MAX_PAID_DISCOVERY_SEARCHES]


def _seed_from_paid_search(job: ArticleJob, client: DataForSEOClient) -> tuple[dict[str, CandidateSeed], list[dict]]:
    seeds: dict[str, CandidateSeed] = {}
    request_logs: list[dict] = []
    suggested_best_for = _suggested_best_for(job)
    for query in _candidate_search_queries(job):
        result = client.fetch_google_serp(query, depth=10)
        request_logs.append(
            {
                "endpoint": result.endpoint,
                "cost": result.cost,
                "query": query,
                "request_count": 1,
                "response_json": result.response_json,
            }
        )
        items = (result.result[0] or {}).get("items") if result.result else []
        for item in items or []:
            if item.get("type") != "organic":
                continue
            candidate_names = _extract_candidate_names(f"{item.get('title', '')} {item.get('description', '')}")
            for name in candidate_names:
                brand, model_number = _parse_brand_and_model(name)
                domain = item.get("domain")
                key = _normalise_key(name, brand, model_number)
                seed = CandidateSeed(
                    product_name=name,
                    brand=brand,
                    model_number=model_number,
                    source_url=item.get("url"),
                    source_domain=domain,
                    source_type="retailer_serp",
                    reasons=[f"Found via retailer search: {query}"],
                    found_count=1,
                    confidence_score=55,
                    suggested_best_for=suggested_best_for,
                    raw_items=[item],
                )
                if key in seeds:
                    _merge_seed(seeds[key], seed)
                else:
                    seeds[key] = seed
    return seeds, request_logs


def _merge_all(*seed_maps: dict[str, CandidateSeed]) -> dict[str, CandidateSeed]:
    merged: dict[str, CandidateSeed] = {}
    for seed_map in seed_maps:
        for key, seed in seed_map.items():
            if key in merged:
                _merge_seed(merged[key], seed)
            else:
                merged[key] = seed
    return merged


def _existing_candidate_map(db: Session, article_job_id: int) -> dict[str, ProductCandidate]:
    rows = list(db.scalars(select(ProductCandidate).where(ProductCandidate.article_job_id == article_job_id)).all())
    return {_normalise_key(row.product_name, row.brand, row.model_number): row for row in rows}


def _existing_linked_product_keys(job: ArticleJob) -> set[str]:
    keys: set[str] = set()
    for link in getattr(job, "article_product_links", []):
        if not link.product:
            continue
        keys.add(_normalise_key(link.product.name, link.product.brand, link.product.model_number))
    return keys


def discover_product_candidates(
    db: Session,
    job: ArticleJob,
    *,
    allow_paid_fallback: bool = True,
) -> tuple[list[ProductCandidate], list[dict]]:
    competitors = list(
        db.scalars(select(CompetitorPage).where(CompetitorPage.article_job_id == job.id).order_by(desc(CompetitorPage.created_at))).all()
    )
    serp_results = list(
        db.scalars(select(SerpResult).where(SerpResult.article_job_id == job.id).order_by(desc(SerpResult.created_at))).all()
    )
    analysis = db.scalar(
        select(CompetitorAnalysisReport).where(CompetitorAnalysisReport.article_job_id == job.id).order_by(desc(CompetitorAnalysisReport.created_at))
    )
    existing_map = _existing_candidate_map(db, job.id)
    linked_keys = _existing_linked_product_keys(job)

    merged = _merge_all(
        _seed_from_competitors(job, competitors),
        _seed_from_analysis(job, analysis),
        _seed_from_serp(job, serp_results),
    )

    paid_logs: list[dict] = []
    if allow_paid_fallback and len(merged) < 3:
        client = DataForSEOClient()
        paid_seeds, paid_logs = _seed_from_paid_search(job, client)
        merged = _merge_all(merged, paid_seeds)

    saved: list[ProductCandidate] = []
    for key, seed in sorted(merged.items(), key=lambda item: (-item[1].confidence_score, -item[1].found_count, item[1].product_name.lower())):
        if key in linked_keys:
            continue
        if not seed.product_name:
            continue
        status = "suggested"
        needs_review = len(seed.product_name.split()) < 2
        existing = existing_map.get(key)
        if existing:
            if existing.status in {"ignored", "converted"}:
                saved.append(existing)
                continue
            existing.product_name = seed.product_name
            existing.brand = seed.brand
            existing.model_number = seed.model_number
            existing.source_url = seed.source_url
            existing.source_domain = seed.source_domain
            existing.source_type = seed.source_type
            existing.reason_found = " | ".join(seed.reasons)
            existing.found_count = seed.found_count
            existing.confidence_score = seed.confidence_score
            existing.suggested_best_for = seed.suggested_best_for
            existing.status = status if existing.status == "suggested" else existing.status
            existing.raw_json = {"items": seed.raw_items, "needs_review": needs_review}
            db.add(existing)
            saved.append(existing)
            continue

        candidate = ProductCandidate(
            article_job_id=job.id,
            product_name=seed.product_name,
            brand=seed.brand,
            model_number=seed.model_number,
            source_url=seed.source_url,
            source_domain=seed.source_domain,
            source_type=seed.source_type,
            reason_found=" | ".join(seed.reasons),
            found_count=seed.found_count,
            confidence_score=seed.confidence_score,
            suggested_best_for=seed.suggested_best_for,
            status=status,
            raw_json={"items": seed.raw_items, "needs_review": needs_review},
        )
        db.add(candidate)
        saved.append(candidate)

    db.commit()
    for candidate in saved:
        db.refresh(candidate)
    return saved, paid_logs


def list_product_candidates(db: Session, article_job_id: int) -> list[ProductCandidate]:
    return list(
        db.scalars(
            select(ProductCandidate)
            .where(ProductCandidate.article_job_id == article_job_id)
            .order_by(desc(ProductCandidate.updated_at), desc(ProductCandidate.confidence_score), ProductCandidate.product_name.asc())
        ).all()
    )


def approve_product_candidate(db: Session, candidate: ProductCandidate) -> ProductCandidate:
    candidate.status = "approved"
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def ignore_product_candidate(db: Session, candidate: ProductCandidate) -> ProductCandidate:
    candidate.status = "ignored"
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def convert_product_candidate(
    db: Session,
    *,
    candidate: ProductCandidate,
    auto_extract: bool = True,
) -> tuple[ProductCandidate, ArticleJobProduct]:
    if candidate.status == "ignored":
        raise ProductCandidateError("Ignored candidates must be reviewed before conversion.")

    cleaned_url = clean_product_url(candidate.source_url) if candidate.source_url else None
    existing_product = db.scalar(
        select(Product).where(
            Product.name == candidate.product_name,
            Product.brand == candidate.brand,
        )
    )
    if not existing_product:
        existing_product = Product(
            name=candidate.product_name,
            brand=candidate.brand or NOT_CONFIRMED,
            category="dehumidifier",
            product_url=cleaned_url or candidate.source_url,
            model_number=candidate.model_number,
            retailer_domain=candidate.source_domain or NOT_CONFIRMED,
            price_text=NOT_CONFIRMED,
            capacity_text=NOT_CONFIRMED,
            tank_size_text=NOT_CONFIRMED,
            noise_level_text=NOT_CONFIRMED,
            power_use_text=NOT_CONFIRMED,
            warranty_text=NOT_CONFIRMED,
            drainage_text=NOT_CONFIRMED,
            room_size_text=NOT_CONFIRMED,
            review_rating_text=NOT_CONFIRMED,
            review_count_text=NOT_CONFIRMED,
            description_snippet=NOT_CONFIRMED,
            confidence_level="Low",
            confidence_score=30,
            common_positives=NOT_CONFIRMED,
            common_complaints=NOT_CONFIRMED,
            who_should_buy=NOT_CONFIRMED,
            who_should_avoid=NOT_CONFIRMED,
            best_for=NOT_CONFIRMED,
            bottom_line=NOT_CONFIRMED,
            extraction_status="pending",
        )
        db.add(existing_product)
        db.commit()
        db.refresh(existing_product)

    existing_link = db.scalar(
        select(ArticleJobProduct)
        .where(ArticleJobProduct.article_job_id == candidate.article_job_id, ArticleJobProduct.product_id == existing_product.id)
        .options(selectinload(ArticleJobProduct.product))
    )
    if existing_link:
        candidate.status = "converted"
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        return candidate, existing_link

    link = ArticleJobProduct(
        article_job_id=candidate.article_job_id,
        product_id=existing_product.id,
        source_url=cleaned_url or candidate.source_url or "",
        original_source_url=candidate.source_url,
        cleaned_source_url=cleaned_url,
        source_type=candidate.source_type,
        extraction_status="pending",
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    if auto_extract and cleaned_url:
        link = extract_product_for_link(db, link)
    else:
        link = db.scalar(
            select(ArticleJobProduct)
            .where(ArticleJobProduct.id == link.id)
            .options(selectinload(ArticleJobProduct.product))
        )

    candidate.status = "converted"
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate, link
