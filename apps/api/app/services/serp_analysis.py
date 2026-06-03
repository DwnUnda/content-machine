from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import CompetitorAnalysisReport, CompetitorPage, KeywordResearch, SerpResult


def _dominant_intent(page_types: dict[str, int]) -> str:
    commercial = page_types.get("retailer", 0) + page_types.get("affiliate/review site", 0) + page_types.get("manufacturer", 0)
    informational = page_types.get("informational blog", 0) + page_types.get("government/health source", 0) + page_types.get("news/media", 0)
    if commercial > informational:
        return "commercial investigation"
    if informational > commercial:
        return "informational"
    return "mixed"


def analyse_serp_for_job(db: Session, article_job_id: int) -> CompetitorAnalysisReport:
    competitors = list(
        db.scalars(select(CompetitorPage).where(CompetitorPage.article_job_id == article_job_id).order_by(CompetitorPage.created_at.desc())).all()
    )
    serp_results = list(db.scalars(select(SerpResult).where(SerpResult.article_job_id == article_job_id)).all())
    keyword_rows = list(db.scalars(select(KeywordResearch).where(KeywordResearch.article_job_id == article_job_id)).all())

    page_type_counts = Counter(row.page_type or "unknown" for row in competitors)
    heading_counts = Counter()
    question_counts = Counter()
    product_counts = Counter()

    avg_au_score = 0
    if competitors:
        avg_au_score = int(sum(row.australian_relevance_score or 0 for row in competitors) / len(competitors))

    for row in competitors:
        for heading in (row.h2_list or []) + (row.h3_list or []):
            heading_counts[heading] += 1
        for question in row.faq_headings or []:
            question_counts[question] += 1
        for product in row.detected_product_names or []:
            product_counts[product] += 1

    competitor_gaps: list[str] = []
    australian_context_gaps: list[str] = []
    original_value: list[str] = []
    support_articles: list[str] = []

    if avg_au_score < 45:
        australian_context_gaps.append("Many ranking pages have weak Australian context or localisation.")
        original_value.append("Add stronger Australian climate, pricing, and rental context.")
    if not any("running cost" in (row.visible_text_extract or "").lower() for row in competitors):
        competitor_gaps.append("Few competitors discuss running costs clearly.")
        original_value.append("Add a running cost explainer for Australian households.")
    if not any("rental" in (row.visible_text_extract or "").lower() for row in competitors):
        competitor_gaps.append("Rental suitability is under-covered.")
        original_value.append("Add rental-friendly guidance and limitations.")
    if not question_counts:
        competitor_gaps.append("FAQ-style decision support appears thin across ranking pages.")
    if not product_counts:
        competitor_gaps.append("Repeated named products were not strongly surfaced in headings or tables.")

    if keyword_rows:
        support_articles.extend([f"{row.keyword} explained" for row in keyword_rows[:3]])
    else:
        support_articles.extend(["Dehumidifier running costs", "Mould in rental homes", "When a dehumidifier helps"])

    difficulty = "low"
    if len(competitors) >= 5 and ("retailer" in page_type_counts or "affiliate/review site" in page_type_counts):
        difficulty = "medium"
    if len(competitors) >= 5 and page_type_counts.get("retailer", 0) >= 3 and avg_au_score >= 50:
        difficulty = "high"

    report = CompetitorAnalysisReport(
        article_job_id=article_job_id,
        dominant_intent=_dominant_intent(dict(page_type_counts)),
        dominant_page_types_json=dict(page_type_counts),
        common_headings_json=[text for text, _ in heading_counts.most_common(12)],
        common_questions_json=[text for text, _ in question_counts.most_common(10)],
        repeated_products_json=[text for text, _ in product_counts.most_common(10)],
        competitor_gaps_json=competitor_gaps,
        australian_context_gaps_json=australian_context_gaps,
        recommended_angle=(
            "Build an Australian buyer-first guide that compares mould control, running cost, and rental suitability "
            "rather than copying generic retailer list pages."
        ),
        original_value_recommendations_json=original_value or [
            "Summarise buyer complaints",
            "Explain room-size suitability",
            "Add Australian context that competitors miss",
        ],
        suggested_support_articles_json=support_articles,
        difficulty_estimate=difficulty,
        raw_report_json={
            "serp_result_count": len(serp_results),
            "competitor_count": len(competitors),
            "average_australian_score": avg_au_score,
            "page_type_counts": dict(page_type_counts),
        },
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report
