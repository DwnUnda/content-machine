from __future__ import annotations

import json
import re
from collections import Counter

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.entities import ArticleJob, PostType, CompetitorAnalysisReport, CompetitorPage, KeywordResearch, SerpResult
from app.models.entities import AppSetting


def _setting_map(db: Session) -> dict[str, str]:
    rows = db.scalars(select(AppSetting).where(AppSetting.category == "content_rules")).all()
    return {row.key: row.value or "" for row in rows}


def _lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80]


def _reader_profile(job: ArticleJob) -> str:
    if job.target_audience:
        return job.target_audience
    if job.post_type == PostType.INFORMATIONAL_BLOG.value:
        return "Australian homeowner or renter looking for a practical answer before buying anything."
    return "Australian homeowner or renter comparing options and trying to avoid wasting money."


def _reader_pain_points(job: ArticleJob, analysis: CompetitorAnalysisReport | None) -> list[str]:
    points = [
        "Needs a clear answer without generic affiliate fluff.",
        "Wants to know what actually suits an Australian home or rental.",
        "Needs downsides and running costs explained, not just upsides.",
    ]
    for item in (analysis.competitor_gaps_json or [])[:3] if analysis else []:
        points.append(item)
    if "mould" in job.primary_keyword.lower():
        points.append("Wants realistic mould control guidance without overblown health claims.")
    return points[:6]


def _required_sections(job: ArticleJob, settings: dict[str, str]) -> list[str]:
    template_lines = _lines(settings.get("content_rules.article_templates", ""))
    product_post_types = {
        PostType.MONEY_POST.value,
        PostType.SINGLE_PRODUCT_REVIEW.value,
        PostType.PRODUCT_COMPARISON.value,
        PostType.BEST_X_FOR_Y.value,
    }
    methodology_section = "How we chose these products"
    for line in template_lines:
        if job.post_type in product_post_types and line.lower().startswith("money article:"):
            sections = [part.strip() for part in line.split(":", 1)[1].split("|")]
            if not any("how we chose" in section.lower() for section in sections):
                sections.append(methodology_section)
            return sections
        if job.post_type == PostType.INFORMATIONAL_BLOG.value and line.lower().startswith("informational article:"):
            return [part.strip() for part in line.split(":", 1)[1].split("|")]
    if job.post_type in product_post_types:
        return ["quick answer", "how we researched", methodology_section, "FAQ", "final recommendation"]
    return ["quick answer", "how we researched", "FAQ", "final recommendation"]


def _source_requirements(job: ArticleJob) -> list[str]:
    base = [
        "Prefer Australian government, health, standards, and manufacturer sources where relevant.",
        "Back every product or feature claim with a stored source, retailer listing, or published specification.",
        "Use honest wording when products were not personally tested.",
    ]
    if "mould" in job.primary_keyword.lower() or "humidity" in job.primary_keyword.lower():
        base.insert(0, "Use careful, non-medical wording for mould, damp, humidity, and indoor air quality claims.")
    return base


def _forbidden_claims() -> list[str]:
    return [
        "Do not invent prices, specs, warranties, availability, star ratings, review counts, or test results.",
        "Do not claim hands-on testing unless personally_tested=true exists for that product.",
        "Do not make medical claims or imply a dehumidifier magically fixes severe mould problems.",
        "If a detail is missing, say Not confirmed or omit the claim.",
    ]


def _title_options(job: ArticleJob, analysis: CompetitorAnalysisReport | None) -> list[str]:
    keyword = job.primary_keyword.strip()
    options = [
        keyword.title(),
        f"{keyword.title()}: What Actually Suits an Australian Home?",
        f"{keyword.title()} for Australian Homes: What to Buy and What to Skip",
    ]
    if analysis and analysis.recommended_angle:
        options.append(f"{keyword.title()}: A Practical Australian Buyer's Guide")
    return options[:4]


def _meta_description(job: ArticleJob, analysis: CompetitorAnalysisReport | None) -> str:
    angle = analysis.recommended_angle if analysis and analysis.recommended_angle else "practical Australian buying advice"
    text = f"Research-backed guide to {job.primary_keyword} with Australian context, product drawbacks, buyer tips, and {angle.lower()}."
    return text[:160]


def build_research_brief_payload(db: Session, job: ArticleJob) -> dict:
    settings = _setting_map(db)
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
    competitors = list(
        db.scalars(
            select(CompetitorPage)
            .where(CompetitorPage.article_job_id == job.id)
            .order_by(desc(CompetitorPage.created_at))
        ).all()
    )
    analysis = db.scalar(
        select(CompetitorAnalysisReport)
        .where(CompetitorAnalysisReport.article_job_id == job.id)
        .order_by(desc(CompetitorAnalysisReport.created_at))
    )

    secondary_keywords: list[str] = []
    for row in keyword_rows:
        if row.keyword.lower() != job.primary_keyword.lower() and row.keyword not in secondary_keywords:
            secondary_keywords.append(row.keyword)
        if len(secondary_keywords) >= 8:
            break

    question_pool = list(analysis.common_questions_json or []) if analysis else []
    if not question_pool:
        seen_questions: set[str] = set()
        for competitor in competitors:
            for question in competitor.faq_headings or []:
                if question not in seen_questions:
                    seen_questions.add(question)
                    question_pool.append(question)
        question_pool = question_pool[:8]

    repeated_products = list(analysis.repeated_products_json or []) if analysis else []
    if not repeated_products:
        product_counts = Counter()
        for competitor in competitors:
            for name in competitor.detected_product_names or []:
                product_counts[name] += 1
        repeated_products = [name for name, _ in product_counts.most_common(8)]

    search_intent = analysis.dominant_intent if analysis and analysis.dominant_intent else "mixed"
    recommended_angle = (
        analysis.recommended_angle
        if analysis and analysis.recommended_angle
        else "Answer the keyword directly, then help Australian readers choose based on room size, running cost, and drawbacks."
    )
    original_value_points = list(analysis.original_value_recommendations_json or []) if analysis else []
    if not original_value_points:
        original_value_points = [
            "Add Australian climate and rental context competitors miss.",
            "Summarise common buyer complaints and who should avoid each option.",
            "Explain running costs and use-case trade-offs in plain English.",
        ]

    support_articles = list(analysis.suggested_support_articles_json or []) if analysis else []
    competitor_gaps = list(analysis.competitor_gaps_json or []) if analysis else []
    australian_context_gaps = list(analysis.australian_context_gaps_json or []) if analysis else []
    page_type_counts = dict(analysis.dominant_page_types_json or {}) if analysis else {}
    top_serp_urls = [row.url for row in serp_rows if row.url][:10]

    tone_rules = _lines(settings.get("content_rules.brand_tone_rules", ""))
    forbidden_phrases = _lines(settings.get("content_rules.forbidden_phrases", ""))
    preferred_phrases = _lines(settings.get("content_rules.preferred_phrases", ""))
    australian_spelling = _lines(settings.get("content_rules.australian_spelling_rules", ""))
    required_sections = _required_sections(job, settings)

    product_requirements: list[str] = []
    product_review_methodology = ""
    tested_language_rules: list[str] = []
    if job.post_type in {
        PostType.MONEY_POST.value,
        PostType.SINGLE_PRODUCT_REVIEW.value,
        PostType.PRODUCT_COMPARISON.value,
        PostType.BEST_X_FOR_Y.value,
    }:
        product_requirements = _lines(settings.get("content_rules.product_section_template", ""))
        product_review_methodology = settings.get("content_rules.product_review_methodology", "").strip()
        tested_language_rules = _lines(settings.get("content_rules.tested_language_rules", ""))

    source_requirements = _source_requirements(job)
    title_options = _title_options(job, analysis)
    meta_description = _meta_description(job, analysis)

    payload = {
        "primary_keyword": job.primary_keyword,
        "secondary_keywords": secondary_keywords,
        "search_intent": search_intent,
        "reader_profile": _reader_profile(job),
        "reader_pain_points": _reader_pain_points(job, analysis),
        "post_type": job.post_type,
        "recommended_article_angle": recommended_angle,
        "competitor_gaps": competitor_gaps,
        "australian_context_gaps": australian_context_gaps,
        "required_sections": required_sections,
        "original_value_points": original_value_points,
        "product_requirements": product_requirements,
        "product_review_methodology": product_review_methodology,
        "tested_language_rules": tested_language_rules,
        "source_requirements": source_requirements,
        "internal_link_suggestions": support_articles,
        "faq_questions": question_pool,
        "forbidden_claims": _forbidden_claims(),
        "tone_rules": tone_rules,
        "forbidden_phrases": forbidden_phrases,
        "preferred_phrases": preferred_phrases,
        "australian_spelling_rules": australian_spelling,
        "suggested_title_options": title_options,
        "suggested_slug": _slugify(job.primary_keyword),
        "meta_description_draft": meta_description,
        "analysis_notes": {
            "top_serp_urls": top_serp_urls,
            "dominant_page_types": page_type_counts,
            "repeated_products": repeated_products,
            "competitor_count": len(competitors),
        },
    }
    return payload


def render_research_brief_markdown(payload: dict) -> str:
    lines = [
        "# Research Brief",
        "",
        f"## Primary keyword\n- {payload['primary_keyword']}",
        "",
        "## Secondary keywords",
    ]
    lines.extend([f"- {item}" for item in payload["secondary_keywords"]] or ["- Not confirmed"])
    lines.extend(
        [
            "",
            f"## Search intent\n- {payload['search_intent']}",
            "",
            f"## Reader profile\n- {payload['reader_profile']}",
            "",
            "## Reader pain points",
        ]
    )
    lines.extend([f"- {item}" for item in payload["reader_pain_points"]])
    lines.extend(
        [
            "",
            f"## Post type\n- {payload['post_type']}",
            "",
            "## Recommended article angle",
            f"- {payload['recommended_article_angle']}",
            "",
            "## Competitor gaps",
        ]
    )
    lines.extend([f"- {item}" for item in payload["competitor_gaps"]] or ["- Not confirmed"])
    lines.extend(["", "## Australian context gaps"])
    lines.extend([f"- {item}" for item in payload["australian_context_gaps"]] or ["- Not confirmed"])
    lines.extend(["", "## Required sections"])
    lines.extend([f"- {item}" for item in payload["required_sections"]])
    lines.extend(["", "## Original value points"])
    lines.extend([f"- {item}" for item in payload["original_value_points"]])
    if payload["product_requirements"]:
        lines.extend(["", "## Product recommendation blocks (review-led, use all in order)"])
        lines.extend([f"- {item}" for item in payload["product_requirements"]])
    if payload.get("product_review_methodology"):
        lines.extend(["", "## How we chose these products (methodology)"])
        lines.append(f"- {payload['product_review_methodology']}")
    if payload.get("tested_language_rules"):
        lines.extend(["", "## Tested vs review-led language rules"])
        lines.extend([f"- {item}" for item in payload["tested_language_rules"]])
    lines.extend(["", "## Source requirements"])
    lines.extend([f"- {item}" for item in payload["source_requirements"]])
    lines.extend(["", "## Internal link suggestions"])
    lines.extend([f"- {item}" for item in payload["internal_link_suggestions"]] or ["- Not confirmed"])
    lines.extend(["", "## FAQ questions"])
    lines.extend([f"- {item}" for item in payload["faq_questions"]] or ["- Not confirmed"])
    lines.extend(["", "## Forbidden claims"])
    lines.extend([f"- {item}" for item in payload["forbidden_claims"]])
    lines.extend(["", "## Tone rules"])
    lines.extend([f"- {item}" for item in payload["tone_rules"]])
    lines.extend(["", "## Forbidden phrases"])
    lines.extend([f"- {item}" for item in payload["forbidden_phrases"]])
    lines.extend(["", "## Preferred phrases"])
    lines.extend([f"- {item}" for item in payload["preferred_phrases"]])
    lines.extend(["", "## Australian spelling rules"])
    lines.extend([f"- {item}" for item in payload["australian_spelling_rules"]])
    lines.extend(["", "## Suggested title options"])
    lines.extend([f"- {item}" for item in payload["suggested_title_options"]])
    lines.extend(
        [
            "",
            f"## Suggested slug\n- {payload['suggested_slug']}",
            "",
            f"## Meta description draft\n- {payload['meta_description_draft']}",
            "",
            "## Analysis notes",
            "```json",
            json.dumps(payload["analysis_notes"], indent=2),
            "```",
        ]
    )
    return "\n".join(lines)
