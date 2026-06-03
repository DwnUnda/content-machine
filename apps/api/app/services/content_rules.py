import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AppSetting


CONTENT_RULE_DEFAULTS = [
    {
        "key": "content_rules.forbidden_phrases",
        "label": "Forbidden phrases",
        "description": "Phrases that make drafts sound generic, corporate, or AI-generated.",
        "category": "content_rules",
        "value": "\n".join(
            [
                "In today's fast-paced world",
                "When it comes to",
                "Dive into",
                "Unlock",
                "Game changer",
                "Elevate",
                "It is important to note",
                "Whether you're",
                "Robust solution",
                "Seamless",
                "Revolutionise",
                "Cutting-edge",
                "Designed to meet your needs",
                "Perfect for every home",
            ]
        ),
    },
    {
        "key": "content_rules.preferred_phrases",
        "label": "Preferred phrases",
        "description": "Preferred Home Dry Lab phrasing for honest, grounded recommendations.",
        "category": "content_rules",
        "value": "\n".join(
            [
                "Based on manufacturer specifications, Australian retailer listings and repeated buyer feedback patterns",
                "Buyer reviews suggest",
                "Published specs list",
                "Retailer information shows",
                "We found repeated complaints about",
                "Not confirmed",
            ]
        ),
    },
    {
        "key": "content_rules.australian_spelling_rules",
        "label": "Australian spelling rules",
        "description": "Australian English replacements and preferred local phrasing.",
        "category": "content_rules",
        "value": "\n".join(
            [
                "mould, not mold",
                "colour, not color",
                "favourite, not favorite",
                "power bill, not utility bill",
                "laundry, not laundry room",
                "running cost, not energy expense",
            ]
        ),
    },
    {
        "key": "content_rules.article_templates",
        "label": "Article templates",
        "description": "Required article structures for money and informational posts.",
        "category": "content_rules",
        "value": (
            "Money article: quick answer | comparison table | how we researched | product recommendations | "
            "buyer decision guide | common mistakes | FAQ | final recommendation\n"
            "Informational article: direct answer near the top | clear explanation | Australian home context | "
            "practical steps | when to consider a product | when to seek professional help if relevant | FAQ"
        ),
    },
    {
        "key": "content_rules.product_section_template",
        "label": "Product section template",
        "description": "Mandatory review-led blocks for each product recommendation.",
        "category": "content_rules",
        "value": "\n".join(
            [
                "Best for",
                "Why it made the list",
                "What users like",
                "Common complaints",
                "Specs that matter",
                "Best fit",
                "Avoid if",
            ]
        ),
    },
    {
        "key": "content_rules.product_review_methodology",
        "label": "Product review methodology",
        "description": "Reader-facing 'How we chose these products' methodology for buying guides, roundups, comparisons and review articles.",
        "category": "content_rules",
        "value": (
            "Every buying guide, product roundup, comparison or review article must include a "
            "short reader-facing section titled 'How we chose these products'. It should explain "
            "that Home Dry Lab considers real customer feedback, recurring review patterns, "
            "product specifications, Australian availability and use-case fit. Keep it honest and "
            "concise. Do not claim hands-on testing unless every featured product is marked "
            "personally tested."
        ),
    },
    {
        "key": "content_rules.tested_language_rules",
        "label": "Tested vs review-led language rules",
        "description": "Controls testing-claim language based on each product's personally_tested flag.",
        "category": "content_rules",
        "value": (
            "Only use first-hand testing language when a product's personally_tested flag is true.\n"
            "Allowed only when personally_tested=true: We tested | In our lab | During our hands-on review | Our testing found\n"
            "When personally_tested is false or missing, use review-led language instead: "
            "Based on customer feedback | Users commonly report | Reviewers often mention | "
            "Across customer reviews, the recurring theme is | Product specs suggest\n"
            "Never claim Home Dry Lab tested, trialled, or used a product that is not marked personally tested."
        ),
    },
    {
        "key": "content_rules.qa_scoring_rules",
        "label": "QA scoring rules",
        "description": "Rubric used to score article quality and review readiness.",
        "category": "content_rules",
        "value": json.dumps(
            {
                "threshold": 85,
                "checks": [
                    "Australian English",
                    "no fake testing claims",
                    "no first-hand testing language unless product personally_tested=true",
                    "review-led product sections use the seven required blocks",
                    "buying guides include a How we chose these products methodology section",
                    "no unsupported specs",
                    "no AI slop phrases",
                    "clear search intent match",
                    "clear recommendations",
                    "product drawbacks included",
                    "Australian context included",
                    "evidence-backed claims",
                    "internal links reviewed before publishing (advisory during draft QA)",
                    "readable formatting",
                    "original value included",
                ],
            },
            indent=2,
        ),
    },
    {
        "key": "content_rules.brand_tone_rules",
        "label": "Brand tone rules",
        "description": "Tone rules for Home Dry Lab articles.",
        "category": "content_rules",
        "value": "\n".join(
            [
                "plain English",
                "practical",
                "direct",
                "helpful",
                "natural",
                "research-backed",
                "human-sounding",
                "not corporate",
                "not overly polished",
                "not fake-expert sounding",
            ]
        ),
    },
    {
        "key": "content_rules.affiliate_disclosure_wording",
        "label": "Affiliate disclosure wording",
        "description": "Preferred affiliate disclosure wording for Home Dry Lab.",
        "category": "content_rules",
        "value": "If we use affiliate links, explain that they may earn Home Dry Lab a commission at no extra cost to the reader.",
    },
    {
        "key": "content_rules.research_disclosure_wording",
        "label": "Research disclosure wording",
        "description": "Preferred research disclosure wording when products are not personally tested.",
        "category": "content_rules",
        "value": "This article is based on manufacturer specifications, Australian retailer listings, authoritative sources, and recurring buyer feedback patterns unless otherwise stated.",
    },
]

CONTENT_RULE_METADATA = {item["key"]: item for item in CONTENT_RULE_DEFAULTS}


def ensure_content_rule_defaults(db: Session) -> None:
    existing = {
        item.key: item
        for item in db.scalars(select(AppSetting).where(AppSetting.category == "content_rules")).all()
    }
    changed = False
    for item in CONTENT_RULE_DEFAULTS:
        if item["key"] not in existing:
            db.add(
                AppSetting(
                    key=item["key"],
                    value=item["value"],
                    description=item["description"],
                    category=item["category"],
                )
            )
            changed = True
    if changed:
        db.commit()


def list_content_rules(db: Session) -> list[AppSetting]:
    ensure_content_rule_defaults(db)
    return list(
        db.scalars(
            select(AppSetting)
            .where(AppSetting.category == "content_rules")
            .order_by(AppSetting.key.asc())
        ).all()
    )


def update_content_rule(db: Session, key: str, value: str) -> AppSetting | None:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if not setting:
        return None
    setting.value = value
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


def get_qa_threshold(db: Session) -> int:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == "content_rules.qa_scoring_rules"))
    if not setting or not setting.value:
        return 85
    try:
        payload = json.loads(setting.value)
    except json.JSONDecodeError:
        return 85
    threshold = payload.get("threshold", 85)
    return int(threshold)
